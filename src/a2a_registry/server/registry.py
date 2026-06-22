"""Registry storage — abstract interface and in-memory default implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from ..models import AgentCard, AgentStatus, RegistryEntry


class RegistryProvider(ABC):
    """Pluggable backend for storing registered agents."""

    @abstractmethod
    async def upsert(self, agent_card: AgentCard, interval: int) -> None:
        """Insert or update an agent; always refreshes last_heartbeat."""

    @abstractmethod
    async def get(self, agent_url: str) -> Optional[RegistryEntry]:
        """Return the entry for the given agent URL, or None."""

    @abstractmethod
    async def mark_verified(self, agent_url: str) -> None:
        """Promote an agent to AgentStatus.available."""

    @abstractmethod
    async def unregister(self, agent_url: str) -> None:
        """Remove an agent from the registry."""

    @abstractmethod
    async def list_available(self) -> List[AgentCard]:
        """Return all agent cards with status == available."""

    @abstractmethod
    async def get_stale(self, multiplier: int = 3) -> List[str]:
        """Return URLs of agents whose last heartbeat is older than multiplier * interval."""


class MemoryRegistryProvider(RegistryProvider):
    """Thread-safe in-memory registry (suitable for single-process deployments)."""

    def __init__(self) -> None:
        self._store: Dict[str, RegistryEntry] = {}

    async def upsert(self, agent_card: AgentCard, interval: int) -> None:
        key = agent_card.effective_url
        existing = self._store.get(key)
        if existing is not None:
            existing.agent_card = agent_card
            existing.interval = interval
            existing.last_heartbeat = datetime.now(tz=timezone.utc)
        else:
            self._store[key] = RegistryEntry(
                agent_card=agent_card,
                last_heartbeat=datetime.now(tz=timezone.utc),
                interval=interval,
                status=AgentStatus.unverified,
            )

    async def get(self, agent_url: str) -> Optional[RegistryEntry]:
        return self._store.get(agent_url)

    async def mark_verified(self, agent_url: str) -> None:
        entry = self._store.get(agent_url)
        if entry is not None:
            entry.status = AgentStatus.available

    async def unregister(self, agent_url: str) -> None:
        self._store.pop(agent_url, None)

    async def list_available(self) -> List[AgentCard]:
        return [
            e.agent_card
            for e in self._store.values()
            if e.status == AgentStatus.available
        ]

    async def get_stale(self, multiplier: int = 3) -> List[str]:
        now = datetime.now(tz=timezone.utc)
        return [
            url
            for url, entry in self._store.items()
            if now - entry.last_heartbeat > timedelta(seconds=entry.interval * multiplier)
        ]
