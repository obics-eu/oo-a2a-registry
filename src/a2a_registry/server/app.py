"""AgentRegistryServer — FastAPI integration and standalone app factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, List, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, FastAPI, Header

from ..models import AgentCard, AgentStatus, HeartbeatRequest, HeartbeatResponse, to_v1, to_v03
from .registry import MemoryRegistryProvider, RegistryProvider
from . import config as server_config

logger = logging.getLogger(__name__)

# A2A well-known paths: v1.0 uses agent-card.json, v0.3 used agent.json
_AGENT_CARD_PATH_V1 = "/.well-known/agent-card.json"
_AGENT_CARD_PATH_V03 = "/.well-known/agent.json"
AGENTS_ENDPOINT = "/.well-known/agents"
HEARTBEAT_ENDPOINT = "/registry/heartbeat"


def _origin(url: str) -> str:
    """Extract scheme://host:port from a URL for .well-known discovery."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


class AgentRegistryServer:
    """
    Core registry logic. Mount into an existing FastAPI app via ``setup(app)``,
    or get a ready-to-serve standalone app via ``create_app()``.

    Parameters
    ----------
    provider:
        Storage backend. Defaults to :class:`MemoryRegistryProvider`.
    stale_multiplier:
        An agent is evicted when its last heartbeat is older than
        ``stale_multiplier * interval`` seconds (default 3).
    cleanup_interval:
        How often (in seconds) the background cleanup task runs (default 30).
    fetch_timeout:
        HTTP timeout (seconds) when fetching a remote agent card (default 10).
    """

    def __init__(
        self,
        provider: Optional[RegistryProvider] = None,
        stale_multiplier: int = 3,
        cleanup_interval: int = 30,
        fetch_timeout: float = 10.0,
    ) -> None:
        self.provider = provider or MemoryRegistryProvider()
        self.stale_multiplier = stale_multiplier
        self.cleanup_interval = cleanup_interval
        self.fetch_timeout = fetch_timeout
        self._cleanup_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_router(self) -> APIRouter:
        """Return a FastAPI router with the registry endpoints."""
        router = APIRouter()

        @router.get(AGENTS_ENDPOINT, response_model=List[AgentCard])
        async def list_agents(
            a2a_version: Optional[str] = Header(None),
        ) -> List[AgentCard]:
            """Return all verified agents, serialised in the requested A2A version.

            The ``A2A-Version`` request header controls the output format
            (``"1.0"`` or ``"0.3"``).  Falls back to the ``A2A_VERSION``
            environment variable (default ``"1.0"``) when the header is absent.
            """
            effective_version = a2a_version or server_config.get_a2a_version()
            cards = await self.provider.list_available()
            if effective_version.startswith("0"):
                return [to_v03(c) for c in cards]
            return [to_v1(c) for c in cards]

        @router.post(HEARTBEAT_ENDPOINT, response_model=HeartbeatResponse)
        async def receive_heartbeat(
            request: HeartbeatRequest,
            a2a_version: Optional[str] = Header(None),  # noqa: ARG001 — informational
        ) -> HeartbeatResponse:
            """Accept a heartbeat from an agent client."""
            return await self._handle_heartbeat(request)

        return router

    def setup(self, app: FastAPI) -> None:
        """
        Integrate the registry into an *existing* FastAPI application.

        Mounts the router and wires startup / shutdown lifecycle hooks.
        """
        app.include_router(self.build_router())
        app.router.on_startup.append(self.start_cleanup)
        app.router.on_shutdown.append(self.stop_cleanup)

    def create_app(self, *, mcp: bool = False) -> FastAPI:
        """Create and return a standalone FastAPI application.

        Parameters
        ----------
        mcp:
            Mount MCP SSE endpoints (``/mcp/sse``, ``/mcp/messages``) so
            registered agent cards are consumable as MCP resources.
            Requires ``pip install oo-a2a-registry[mcp]``.
        """

        @asynccontextmanager
        async def lifespan(_: FastAPI) -> AsyncIterator[None]:
            await self.start_cleanup()
            yield
            await self.stop_cleanup()

        app = FastAPI(
            title="A2A Agent Registry",
            description="Agent discovery registry for A2A agents",
            version="0.1.0",
            lifespan=lifespan,
        )
        app.include_router(self.build_router())
        if mcp:
            self.mount_mcp(app)
        return app

    def mount_mcp(self, app: FastAPI) -> None:
        """Mount MCP SSE endpoints onto *app*.

        Exposes registered agent cards as MCP resources at:
            GET  /mcp/sse       — SSE stream
            POST /mcp/messages  — JSON-RPC messages

        Requires ``pip install oo-a2a-registry[mcp]``.
        """
        try:
            from .mcp_server import mount_mcp_server
        except ImportError as exc:
            raise ImportError(
                "MCP support requires the 'mcp' package: "
                "pip install 'oo-a2a-registry[mcp]'"
            ) from exc
        mount_mcp_server(app, self.provider)

    async def start_cleanup(self) -> None:
        """Start the background task that evicts stale agents."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("Registry cleanup task started (interval=%ds)", self.cleanup_interval)

    async def stop_cleanup(self) -> None:
        """Cancel the background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Registry cleanup task stopped.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _handle_heartbeat(self, request: HeartbeatRequest) -> HeartbeatResponse:
        card = request.agent_card
        agent_url = card.effective_url
        existing = await self.provider.get(agent_url)

        # Already verified → just refresh the timestamp
        if existing is not None and existing.status == AgentStatus.available:
            await self.provider.upsert(card, request.interval)
            return HeartbeatResponse(status="ok", verified=True)

        # New or unverified agent → attempt remote verification
        fetched = await self._fetch_agent_card(card)
        if fetched:
            await self.provider.upsert(fetched, request.interval)
            await self.provider.mark_verified(agent_url)
            logger.info("Agent verified and registered: %s", agent_url)
            return HeartbeatResponse(status="ok", verified=True)

        # Verification failed — store as unverified so subsequent heartbeats can retry
        await self.provider.upsert(card, request.interval)
        logger.debug("Heartbeat accepted but agent not yet verified: %s", agent_url)
        return HeartbeatResponse(status="ok", verified=False)

    async def _fetch_agent_card(self, agent_card: AgentCard) -> Optional[AgentCard]:
        """Fetch the agent's published card from its /.well-known endpoint.

        For v1.0 agents (with supportedInterfaces) tries agent-card.json first,
        then falls back to agent.json. For v0.3 agents the order is reversed.
        """
        base = _origin(agent_card.effective_url)

        if agent_card.supportedInterfaces is not None:
            paths = (_AGENT_CARD_PATH_V1, _AGENT_CARD_PATH_V03)
        else:
            paths = (_AGENT_CARD_PATH_V03, _AGENT_CARD_PATH_V1)

        async with httpx.AsyncClient() as client:
            for path in paths:
                url = base + path
                try:
                    resp = await client.get(url, timeout=self.fetch_timeout)
                    resp.raise_for_status()
                    return AgentCard.model_validate(resp.json())
                except Exception as exc:
                    logger.debug("Could not fetch agent card from %s: %s", url, exc)

        logger.warning("Could not fetch agent card for %s", base)
        return None

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.cleanup_interval)
                stale = await self.provider.get_stale(self.stale_multiplier)
                for url in stale:
                    logger.info("Evicting stale agent: %s", url)
                    await self.provider.unregister(url)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in registry cleanup loop")
