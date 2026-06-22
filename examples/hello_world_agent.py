"""
Hello World A2A agent using official A2A SDK types.

The agent card is built with ``a2a.types.AgentCard`` (protobuf), converted
to the registry's Pydantic model for the heartbeat client, and served
directly from the protobuf serialisation on the well-known endpoint.

Install:
    pip install "oo-a2a-registry[server]" a2a-sdk

Run (start the registry first):
    python examples/registry_server.py          # terminal 1
    python examples/hello_world_agent.py        # terminal 2

Verify:
    curl -s http://localhost:8000/.well-known/agents | python -m json.tool
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a_registry import RegistryClient
from a2a_registry.models import AgentCard as RegistryCard

AGENT_BASE_URL = "http://localhost:8001"
REGISTRY_URL = "http://localhost:8000"


def _build_card() -> AgentCard:
    iface = AgentInterface()
    iface.url = f"{AGENT_BASE_URL}/jsonrpc"
    iface.protocol_binding = "json-rpc/2.0"
    iface.protocol_version = "1.0"

    skill = AgentSkill()
    skill.id = "greet"
    skill.name = "Greet"
    skill.description = "Say hello to anyone."
    skill.tags.extend(["greeting", "hello"])
    skill.input_modes.extend(["text/plain"])
    skill.output_modes.extend(["text/plain"])

    card = AgentCard()
    card.name = "Hello World Agent"
    card.description = "A minimal A2A agent that greets the world."
    card.version = "1.0.0"
    card.supported_interfaces.append(iface)
    card.capabilities.CopyFrom(AgentCapabilities())
    card.skills.append(skill)
    card.default_input_modes.extend(["text/plain"])
    card.default_output_modes.extend(["text/plain"])
    return card


_a2a_card = _build_card()
_registry_card = RegistryCard.model_validate(MessageToDict(_a2a_card))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with RegistryClient(REGISTRY_URL, _registry_card, interval=30):
        yield


app = FastAPI(title="Hello World Agent", lifespan=lifespan)


@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
async def agent_card():
    return MessageToDict(_a2a_card)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
