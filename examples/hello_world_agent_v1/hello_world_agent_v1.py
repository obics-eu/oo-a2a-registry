"""
Hello World A2A agent — multiple interfaces using official A2A SDK types.

Demonstrates advertising two protocol bindings (JSON-RPC and gRPC) in a
single A2A v1.0 agent card built with ``a2a.types``.

Setup (from this directory):
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt

Run (start the registry first):
    ../registry_server/.venv/bin/python ../registry_server/registry_server.py  # terminal 1
    .venv/bin/python hello_world_agent_v1.py                                   # terminal 2

Verify:
    curl -s http://localhost:8000/.well-known/agents | python -m json.tool

Environment:
    PORT         — port to listen on (default 8002)
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

PORT = int(os.getenv("PORT", "8002"))
AGENT_BASE_URL = f"http://localhost:{PORT}"
REGISTRY_URL = os.getenv("REGISTRY_URL", "http://localhost:8000")


def _build_card() -> AgentCard:
    jsonrpc_iface = AgentInterface()
    jsonrpc_iface.url = f"{AGENT_BASE_URL}/jsonrpc"
    jsonrpc_iface.protocol_binding = "json-rpc/2.0"
    jsonrpc_iface.protocol_version = "1.0"

    grpc_iface = AgentInterface()
    grpc_iface.url = "http://localhost:50051"
    grpc_iface.protocol_binding = "grpc"
    grpc_iface.protocol_version = "1.0"

    skill = AgentSkill()
    skill.id = "greet"
    skill.name = "Greet"
    skill.description = "Say hello to anyone."
    skill.tags.extend(["greeting", "hello"])
    skill.input_modes.extend(["text/plain"])
    skill.output_modes.extend(["text/plain"])

    caps = AgentCapabilities()
    caps.streaming = True

    card = AgentCard()
    card.name = "Hello World Agent (multi-interface)"
    card.description = "A2A v1.0 agent advertising JSON-RPC and gRPC interfaces."
    card.version = "1.0.0"
    card.supported_interfaces.extend([jsonrpc_iface, grpc_iface])
    card.capabilities.CopyFrom(caps)
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


app = FastAPI(title="Hello World Agent v1.0", lifespan=lifespan)


@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
async def agent_card():
    return MessageToDict(_a2a_card)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
