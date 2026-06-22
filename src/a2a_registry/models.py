"""Shared A2A-compatible data models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class AgentProvider(BaseModel):
    organization: str
    url: Optional[str] = None


class AgentCapabilities(BaseModel):
    streaming: bool = False
    pushNotifications: bool = False
    stateTransitionHistory: bool = False
    extendedAgentCard: Optional[bool] = None  # A2A v1.0


class AgentSkill(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    examples: Optional[List[str]] = None
    inputModes: Optional[List[str]] = None
    outputModes: Optional[List[str]] = None


class AgentInterface(BaseModel):
    """A2A v1.0 interface descriptor inside supportedInterfaces."""

    url: str
    protocolBinding: Optional[str] = None  # e.g. "json-rpc/2.0"
    protocolVersion: Optional[str] = None  # e.g. "1.0"
    tenant: Optional[str] = None

    model_config = {"extra": "allow"}


class AgentCard(BaseModel):
    """A2A-compatible agent card (v0.3 and v1.0).

    Discovery paths:
      v0.3: /.well-known/agent.json       — top-level ``url`` field present
      v1.0: /.well-known/agent-card.json  — ``url`` lives inside ``supportedInterfaces``
    """

    name: str
    description: Optional[str] = None

    # v0.3: top-level base URL (unique registry key); absent in v1.0
    url: Optional[str] = None

    # v1.0: replaces top-level url + preferredTransport + additionalInterfaces
    supportedInterfaces: Optional[List[AgentInterface]] = None

    version: str = "1.0.0"
    provider: Optional[AgentProvider] = None
    documentationUrl: Optional[str] = None
    iconUrl: Optional[str] = None
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    defaultInputModes: List[str] = Field(default_factory=lambda: ["text/plain"])
    defaultOutputModes: List[str] = Field(default_factory=lambda: ["text/plain"])
    skills: List[AgentSkill] = Field(default_factory=list)

    # v0.3-only fields
    protocolVersion: Optional[str] = None       # e.g. "0.3.0" at card level
    preferredTransport: Optional[str] = None    # e.g. "JSONRPC"

    # security (v0.3: security list; v1.0: securityRequirements)
    securitySchemes: Optional[Dict[str, Any]] = None
    security: Optional[List[Dict[str, Any]]] = None              # v0.3
    securityRequirements: Optional[List[Dict[str, Any]]] = None  # v1.0

    model_config = {"extra": "allow"}  # Forward-compatible with A2A spec additions

    @model_validator(mode="after")
    def _require_url_or_interfaces(self) -> "AgentCard":
        if self.url is None and not self.supportedInterfaces:
            raise ValueError(
                "AgentCard must provide either 'url' (A2A v0.3) "
                "or 'supportedInterfaces' (A2A v1.0)"
            )
        return self

    @property
    def effective_url(self) -> str:
        """Canonical agent URL: top-level ``url`` (v0.3) or first interface URL (v1.0)."""
        if self.url:
            return self.url
        return self.supportedInterfaces[0].url  # type: ignore[index]


class AgentStatus(str, Enum):
    available = "available"
    unverified = "unverified"


class RegistryEntry(BaseModel):
    """Internal registry record — not part of the public API response."""

    agent_card: AgentCard
    last_heartbeat: datetime
    interval: int = 60
    status: AgentStatus = AgentStatus.unverified


class HeartbeatRequest(BaseModel):
    """Body sent by the client on every heartbeat POST."""

    agent_card: AgentCard
    interval: int = Field(default=60, ge=1, description="Heartbeat interval in seconds")


class HeartbeatResponse(BaseModel):
    status: str = "ok"
    verified: bool
