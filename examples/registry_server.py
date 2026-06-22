"""
Standalone A2A agent registry server.

Install dependencies:
    pip install oo-a2a-registry[server]

Run:
    python examples/registry_server.py

Endpoints:
    GET  http://localhost:8000/.well-known/agents    — list all verified agents
    POST http://localhost:8000/registry/heartbeat    — accept agent heartbeats
"""

import uvicorn

from a2a_registry import AgentRegistryServer

if __name__ == "__main__":
    server = AgentRegistryServer(
        stale_multiplier=3,    # evict after 3 missed heartbeat intervals
        cleanup_interval=30,   # run cleanup sweep every 30 s
    )
    app = server.create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
