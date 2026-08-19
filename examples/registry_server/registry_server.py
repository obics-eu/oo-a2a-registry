"""
Standalone A2A agent registry server.

Setup (from this directory):
    python -m venv .venv
    .venv/bin/pip install -r requirements.txt

Run:
    .venv/bin/python registry_server.py

Endpoints:
    GET  http://localhost:8000/.well-known/agents           — list all verified agents
    POST http://localhost:8000/.well-known/agents/heartbeat — accept agent heartbeats

Environment:
    PORT — port to listen on (default 8000)
"""

import os

import uvicorn

from a2a_registry import AgentRegistryServer

if __name__ == "__main__":
    server = AgentRegistryServer(
        stale_multiplier=3,    # evict after 3 missed heartbeat intervals
        expected_heartbeat_interval=30,   # run cleanup sweep every 30 s
    )
    app = server.create_app()
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")), log_level="info")
