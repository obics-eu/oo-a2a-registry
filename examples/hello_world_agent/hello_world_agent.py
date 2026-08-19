"""
Hello World A2A agent using official A2A SDK types.

The agent card is built with ``a2a.types.AgentCard`` (protobuf), converted
to the registry's Pydantic model for the heartbeat client, and served
directly from the protobuf serialisation on the well-known endpoint.

The agent is served under a basepath (http://localhost:8001/basepath) to
demonstrate that the registry discovers well-known cards below a basepath,
not only at the bare origin.

Setup (from this directory):
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt

Run (start the registry first):
    ../registry_server/.venv/bin/python ../registry_server/registry_server.py  # terminal 1
    .venv/bin/python hello_world_agent.py                                      # terminal 2

Verify:
    curl -s http://localhost:8000/.well-known/agents | python -m json.tool

Environment:
    PORT         — port to listen on (default 8001)
    REGISTRY_URL — registry base URL (default http://localhost:8000)
"""

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from google.protobuf.json_format import MessageToDict

from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a_registry import RegistryClient
from a2a_registry.models import AgentCard as RegistryCard

PORT = int(os.getenv("PORT", "8001"))
AGENT_BASE_URL = f"http://localhost:{PORT}/basepath"
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")


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


@app.get("/basepath/.well-known/agent-card.json")
@app.get("/basepath/.well-known/agent.json")
async def agent_card():
    return MessageToDict(_a2a_card)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
