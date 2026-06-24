"""RegistryClient — sends periodic heartbeats to an AgentRegistryServer."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from ..models import AgentCard, HeartbeatRequest, HeartbeatResponse, to_v1, to_v03
from ..server.app import HEARTBEAT_ENDPOINT
from . import config as client_config

logger = logging.getLogger(__name__)

_A2A_VERSION_HEADER = "A2A-Version"


class RegistryClient:
    """
    Registers an agent with a remote :class:`AgentRegistryServer` by sending
    a heartbeat POST on a configurable interval.

    The client can be used as an async context manager or started / stopped
    manually.

    Parameters
    ----------
    registry_url:
        Base URL of the registry server (e.g. ``"http://registry:8000"``).
        If *None*, falls back to the ``REGISTRY_URL`` environment variable.
        Raises :exc:`ValueError` if neither is provided.
    agent_card:
        The A2A agent card describing this agent (v0.3 or v1.0).
    interval:
        Heartbeat interval in seconds (default 60).
        The registry uses this value to decide when the agent is stale.
    timeout:
        HTTP request timeout in seconds (default 10).
    a2a_version:
        A2A protocol version used when sending the card (``"1.0"`` or
        ``"0.3"``).  The card is converted to this format before sending,
        regardless of the format it was passed in as.
        Overrides the ``A2A_VERSION`` environment variable.
        Defaults to the ``A2A_VERSION`` env var, or ``"1.0"`` if unset.
    """

    def __init__(
        self,
        registry_url: Optional[str] = None,
        agent_card: Optional[AgentCard] = None,
        interval: Optional[int] = None,
        timeout: float = 10.0,
        a2a_version: Optional[str] = None,
    ) -> None:
        resolved_url = registry_url or client_config.get_registry_url()
        if resolved_url is None:
            raise ValueError(
                "registry_url must be provided or set via the REGISTRY_URL environment variable"
            )
        if agent_card is None:
            raise ValueError("agent_card is required")
        self.registry_url = resolved_url.rstrip("/")
        self.agent_card = agent_card
        self.interval: int = (
            interval if interval is not None else client_config.get_heartbeat_interval()
        )
        self.timeout = timeout
        self.a2a_version = a2a_version or client_config.get_a2a_version()
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background heartbeat task (idempotent)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._heartbeat_loop())
            logger.info(
                "Heartbeat started — agent '%s' → %s (interval=%ds, a2a_version=%s)",
                self.agent_card.name,
                self.registry_url,
                self.interval,
                self.a2a_version,
            )

    async def stop(self) -> None:
        """Cancel the background heartbeat task and wait for it to finish."""
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Heartbeat stopped — agent '%s'", self.agent_card.name)

    async def __aenter__(self) -> "RegistryClient":
        await self.start()
        return self

    async def __aexit__(self, *_) -> None:
        await self.stop()

    # ------------------------------------------------------------------
    # Single-shot helper
    # ------------------------------------------------------------------

    async def send_once(self) -> HeartbeatResponse | None:
        """
        Send one heartbeat immediately.

        The agent card is converted to the configured A2A version before
        sending, independent of the format it was passed in as.
        Returns the parsed :class:`HeartbeatResponse` on success, or ``None``
        if the request failed.
        """
        if self.a2a_version.startswith("0"):
            send_card = to_v03(self.agent_card)
        else:
            send_card = to_v1(self.agent_card)

        url = self.registry_url + HEARTBEAT_ENDPOINT
        payload = HeartbeatRequest(agent_card=send_card, interval=self.interval)
        try:
            async with httpx.AsyncClient() as http:
                resp = await http.post(
                    url,
                    content=payload.model_dump_json(),
                    headers={
                        "Content-Type": "application/json",
                        _A2A_VERSION_HEADER: self.a2a_version,
                    },
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                retry_after = resp.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        new_interval = int(retry_after)
                        if new_interval != self.interval:
                            logger.info(
                                "Adjusting heartbeat interval for '%s': %ds → %ds",
                                self.agent_card.name,
                                self.interval,
                                new_interval,
                            )
                            self.interval = new_interval
                    except ValueError:
                        pass
                return HeartbeatResponse.model_validate(resp.json())
        except Exception as exc:
            logger.warning(
                "Heartbeat failed for agent '%s': %s", self.agent_card.name, exc
            )
            return None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await self.send_once()
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Unexpected error in heartbeat loop for '%s'", self.agent_card.name
                )
                await asyncio.sleep(self.interval)
