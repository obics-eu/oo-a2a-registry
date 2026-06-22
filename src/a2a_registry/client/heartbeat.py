"""RegistryClient — sends periodic heartbeats to an AgentRegistryServer."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import httpx

from ..models import AgentCard, HeartbeatRequest, HeartbeatResponse
from ..server.app import HEARTBEAT_ENDPOINT

logger = logging.getLogger(__name__)


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
    agent_card:
        The A2A agent card describing this agent.
    interval:
        Heartbeat interval in seconds (default 60).
        The registry uses this value to decide when the agent is stale.
    timeout:
        HTTP request timeout in seconds (default 10).
    """

    def __init__(
        self,
        registry_url: str,
        agent_card: AgentCard,
        interval: int = 60,
        timeout: float = 10.0,
    ) -> None:
        self.registry_url = registry_url.rstrip("/")
        self.agent_card = agent_card
        self.interval = interval
        self.timeout = timeout
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background heartbeat task (idempotent)."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._heartbeat_loop())
            logger.info(
                "Heartbeat started — agent '%s' → %s (interval=%ds)",
                self.agent_card.name,
                self.registry_url,
                self.interval,
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

        Returns the parsed :class:`HeartbeatResponse` on success, or ``None``
        if the request failed.
        """
        url = self.registry_url + HEARTBEAT_ENDPOINT
        payload = HeartbeatRequest(agent_card=self.agent_card, interval=self.interval)
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    content=payload.model_dump_json(),
                    headers={"Content-Type": "application/json"},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
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
