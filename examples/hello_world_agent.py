"""
Hello World A2A agent — v0.3 style (top-level url field).

Serves its agent card at /.well-known/agent.json and registers itself
with the local registry every 30 seconds via a background heartbeat.

Install dependencies:
    pip install oo-a2a-registry[server]

Run (start the registry first):
    python examples/registry_server.py          # terminal 1
    python examples/hello_world_agent.py        # terminal 2

Verify the agent appeared in the registry:
    curl -s http://localhost:8000/.well-known/agents | python -m json.tool
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from a2a_registry import AgentCard, AgentCapabilities, AgentSkill, RegistryClient

AGENT_URL = "http://localhost:8001"
REGISTRY_URL = "http://localhost:8000"

card = AgentCard(
    name="Hello World Agent",
    description="A minimal A2A agent that greets the world.",
    url=AGENT_URL,
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
    # RegistryClient sends the first heartbeat immediately on start,
    # then repeats every `interval` seconds until the context exits.
    async with RegistryClient(REGISTRY_URL, card, interval=30):
        yield


app = FastAPI(title="Hello World Agent", lifespan=lifespan)


@app.get("/.well-known/agent.json")
@app.get("/.well-known/agent-card.json")
async def agent_card():
    """Serve the agent card — compatible with both A2A v0.3 and v1.0 discovery."""
    return card.model_dump(exclude_none=True)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
