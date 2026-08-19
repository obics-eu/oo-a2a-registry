# Examples

Each example lives in its own directory with its own `requirements.txt` and is
run from an isolated virtual environment that installs `oo-a2a-registry` from
PyPI — exactly the way a consumer of the package would.

| Directory | Description | Default port |
|-----------|-------------|--------------|
| [`registry_server/`](registry_server/) | Standalone registry server | 8000 |
| [`hello_world_agent/`](hello_world_agent/) | Hello World agent served under a basepath (`/basepath`) | 8001 |
| [`hello_world_agent_v1/`](hello_world_agent_v1/) | Hello World agent advertising JSON-RPC + gRPC interfaces | 8002 |

## Setup

Create a venv and install dependencies in each example directory:

```bash
for d in registry_server hello_world_agent hello_world_agent_v1; do
    (cd "$d" && python -m venv .venv && .venv/bin/pip install -r requirements.txt)
done
```

## Run

```bash
(cd registry_server     && .venv/bin/python registry_server.py)     &  # terminal 1
(cd hello_world_agent   && .venv/bin/python hello_world_agent.py)   &  # terminal 2

curl -s http://localhost:8000/.well-known/agents | python -m json.tool
```

All examples accept a `PORT` environment variable; the agents additionally
accept `REGISTRY_URL` (default `http://localhost:8000`).
