"""oo-a2a-registry — A2A agent registry server and client."""

from .models import (
    AgentCard,
    AgentCapabilities,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    HeartbeatRequest,
    card_a2a_version,
    to_v1,
    to_v03,
)
from .server import AgentRegistryServer, MemoryRegistryProvider, RegistryProvider
from .client import RegistryClient

__all__ = [
    "AgentCard",
    "AgentCapabilities",
    "AgentInterface",
    "AgentProvider",
    "AgentSkill",
    "HeartbeatRequest",
    "card_a2a_version",
    "to_v1",
    "to_v03",
    "AgentRegistryServer",
    "MemoryRegistryProvider",
    "RegistryProvider",
    "RegistryClient",
]

__version__ = "0.1.0"
