"""
Hello World A2A agent — v1.0 style (url inside supportedInterfaces).

In A2A v1.0 the top-level ``url`` field is replaced by a
``supportedInterfaces`` array, where each entry advertises one
protocol binding together with its endpoint URL and version.

The registry discovers this agent via /.well-known/agent-card.json
(the v1.0 well-known path), with fallback to agent.json.

Install dependencies:
    pip install oo-a2a-registry[server]

Run (start the registry first):
    python examples/registry_server.py              # terminal 1
    python examples/hello_world_agent_v1.py         # terminal 2

Verify:
    curl -s http://localhost:8000/.well-known/agents | python -m json.tool
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from a2a_registry import AgentCard, AgentCapabilities, AgentInterface, AgentSkill, RegistryClient

AGENT_BASE_URL = "http://localhost:8002"
REGISTRY_URL = "http://localhost:8000"

card = AgentCard(
    name="Hello World Agent (v1.0)",
    description="A minimal A2A v1.0 agent that greets the world.",
    supportedInterfaces=[
        AgentInterface(
            url=f"{AGENT_BASE_URL}/jsonrpc",
            protocolBinding="json-rpc/2.0",
            protocolVersion="1.0",
        )
    ],
    version="1.0.0",
    capabilities=AgentCapabilities(streaming=False),
    skills=[
        AgentSkill(
            id="greet",
            name="Greet",
            description="Say hello to anyone.",
            tags=["greeting", "hello"],
            examples=["Hello!", "Greet me"],
            inputModes=["text/plain"],
            outputModes=["text/plain"],
        )
    ],
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with RegistryClient(REGISTRY_URL, card, interval=30):
        yield


app = FastAPI(title="Hello World Agent v1.0", lifespan=lifespan)


@app.get("/.well-known/agent-card.json")
@app.get("/.well-known/agent.json")
async def agent_card():
    """Serve the A2A v1.0 agent card."""
    return card.model_dump(exclude_none=True)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002, log_level="info")
