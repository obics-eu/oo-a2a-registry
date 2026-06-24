# oo-a2a-registry

Fast and lean AI agent registry implementing the [A2A protocol](https://a2a-protocol.org/) for agent discovery via heartbeat-based registration.

Supports **A2A v0.3** (top-level `url` field, `agent.json` discovery) and **A2A v1.0** (`supportedInterfaces`, `agent-card.json` discovery).

## Overview

| Component | What it does |
|-----------|--------------|
| **Server** | Exposes `GET /.well-known/agents` returning live A2A agent cards (format controlled by `A2A-Version` request header). Accepts `POST /registry/heartbeat` — responds **202** with `Retry-After` header. Verifies agents by fetching their `.well-known` card once. Evicts agents that exceed `STALE_MULTIPLIER × interval` seconds of silence. |
| **Client** | Sends the agent's `AgentCard` to the registry as a background task. Initial interval defaults to `HEARTBEAT_INTERVAL` env var (60 s) and is automatically adjusted to the server's `Retry-After` value. Converts the card to the configured `A2A_VERSION` format before sending. |

## Installation

```bash
pip install oo-a2a-registry                   # client + server (no ASGI server)
pip install "oo-a2a-registry[server]"         # includes uvicorn
```

## Quick start

### Standalone registry server

```python
import uvicorn
from a2a_registry import AgentRegistryServer

server = AgentRegistryServer()
app = server.create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Mount into an existing FastAPI app

```python
from fastapi import FastAPI
from a2a_registry import AgentRegistryServer

app = FastAPI()
registry = AgentRegistryServer()
registry.setup(app)          # adds /.well-known/agents and /registry/heartbeat
```

### Agent client — A2A v0.3

```python
import asyncio
from a2a_registry import AgentCard, RegistryClient

card = AgentCard(
    name="My Agent",
    url="http://my-agent:8080",   # agent must serve /.well-known/agent.json
    version="1.0.0",
)

async def main():
    async with RegistryClient("http://registry:8000", card, interval=30) as client:
        await asyncio.sleep(300)   # heartbeats run in the background

asyncio.run(main())
```

### Agent client — A2A v1.0

```python
import asyncio
from a2a_registry import AgentCard, AgentInterface, RegistryClient

card = AgentCard(
    name="My Agent",
    supportedInterfaces=[
        AgentInterface(
            url="http://my-agent:8080/jsonrpc",
            protocolBinding="json-rpc/2.0",
            protocolVersion="1.0",
        )
    ],
    version="1.0.0",
)

async def main():
    async with RegistryClient("http://registry:8000", card, interval=30) as client:
        await asyncio.sleep(300)

asyncio.run(main())
```

### Send a single heartbeat

```python
client = RegistryClient("http://registry:8000", card)
result = await client.send_once()
print(result.verified)
```

## Examples

Runnable examples are in the [`examples/`](examples/) directory:

| File | Description |
|------|-------------|
| [`registry_server.py`](examples/registry_server.py) | Standalone registry on port 8000 |
| [`hello_world_agent.py`](examples/hello_world_agent.py) | Hello World agent (A2A v0.3) on port 8001 |
| [`hello_world_agent_v1.py`](examples/hello_world_agent_v1.py) | Hello World agent (A2A v1.0) on port 8002 |

```bash
pip install "oo-a2a-registry[server]"
python examples/registry_server.py &
python examples/hello_world_agent.py &
curl -s http://localhost:8000/.well-known/agents | python -m json.tool
```

## A2A version compatibility

The registry accepts and serves agent cards from both protocol versions.

| | A2A v0.3 | A2A v1.0 |
|---|---|---|
| Agent URL field | top-level `url` | `supportedInterfaces[].url` |
| Discovery path | `/.well-known/agent.json` | `/.well-known/agent-card.json` |
| Protocol version | `protocolVersion` (card-level) | `supportedInterfaces[].protocolVersion` |

Cards without a top-level `url` must provide `supportedInterfaces`. The registry uses `AgentCard.effective_url` as the canonical key.

When verifying an agent the registry tries the preferred discovery path first (based on which fields the heartbeat card has) and falls back to the other automatically.

### Outgoing format — `A2A-Version` header

The **client** adds an `A2A-Version` header to every heartbeat POST, and converts the card to that format regardless of how it was constructed:

```python
# v0.3 card sent as v1.0 (default)
client = RegistryClient("http://registry:8000", v03_card)           # a2a_version="1.0"

# v1.0 card sent as v0.3
client = RegistryClient("http://registry:8000", v1_card, a2a_version="0.3")
```

The **server** honours an `A2A-Version` request header on `GET /.well-known/agents` and converts all returned cards to the requested format. Falls back to the `A2A_VERSION` env var (default `"1.0"`) when no header is present:

```bash
curl -H "A2A-Version: 0.3" http://localhost:8000/.well-known/agents
```

## How it works

```
Agent                              Registry Server
  |                                      |
  |-- POST /registry/heartbeat --------> |
  |   { agent_card, interval }           |
  |   A2A-Version: 1.0                   |
  |                                      |-- GET {origin}/.well-known/agent-card.json  (v1.0)
  |                                      |         — or —
  |                                      |-- GET {origin}/.well-known/agent.json       (v0.3)
  |                                      |   (once, to verify reachability)
  |                                      |-- store as "available"
  |<-- 202 { status: "ok", verified } -- |
  |    Retry-After: 60                   |
  |                                      |
  |-- POST /registry/heartbeat --------> |  (every Retry-After seconds)
  |                                      |-- refresh last_heartbeat timestamp
  |                                      |
  |   (silence > STALE_MULTIPLIER × interval)  |-- evict from registry
```

`GET /.well-known/agents` returns only agents with `status == available`.
The `A2A-Version` request header controls whether cards are returned in v0.3 or v1.0 format.

## MCP support

Install the `mcp` extra to expose registered agent cards as [MCP](https://modelcontextprotocol.io/) resources, making them directly consumable by any MCP client (Claude Desktop, Cursor, etc.):

```bash
pip install "oo-a2a-registry[mcp]"
```

### Enable MCP in the standalone app

```python
server = AgentRegistryServer()
app = server.create_app(mcp=True)   # adds /mcp/sse and /mcp/messages
```

### Mount MCP onto an existing app

```python
server = AgentRegistryServer()
server.setup(app)       # registry endpoints
server.mount_mcp(app)   # MCP endpoints
```

### Resources exposed

| URI | Description |
|-----|-------------|
| `a2a://agents` | JSON array of all currently verified agent cards |
| `a2a://agents/{url}` | Individual agent card (url = percent-encoded agent URL) |

A resource template `a2a://agents/{url}` is also advertised so MCP clients can fetch specific agents by URL.

### Connect Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "a2a-registry": {
      "url": "http://localhost:8000/mcp/sse"
    }
  }
}
```

## Custom storage backend

Implement `RegistryProvider` to plug in Redis, a database, etc.:

```python
from a2a_registry.server import RegistryProvider

class RedisRegistryProvider(RegistryProvider):
    async def upsert(self, agent_card, interval): ...
    async def get(self, agent_url): ...
    async def mark_verified(self, agent_url): ...
    async def unregister(self, agent_url): ...
    async def list_available(self): ...
    async def get_stale(self, multiplier=3): ...

server = AgentRegistryServer(provider=RedisRegistryProvider())
```

## Configuration

All parameters can be set via constructor argument **or** environment variable. The constructor argument takes precedence.

### Server

| Constructor param | Env var | Default | Description |
|-------------------|---------|---------|-------------|
| `stale_multiplier` | `STALE_MULTIPLIER` | `3` | Evict agent after `stale_multiplier × interval` seconds of silence |
| `expected_heartbeat_interval` | `EXPECTED_HEARTBEAT_INTERVAL` | `60` | Expected client interval (s); returned in `Retry-After` and drives cleanup sweeps |
| `fetch_timeout` | `FETCH_TIMEOUT` | `10.0` | Timeout (s) for fetching remote agent cards during verification |
| *(response format)* | `A2A_VERSION` | `1.0` | Default A2A format for `GET /.well-known/agents` when no `A2A-Version` request header is sent |
| *(storage path)* | `REGISTRY_PATH` | `.` | Filesystem path for persistent storage backends |

### Client

| Constructor param | Env var | Default | Description |
|-------------------|---------|---------|-------------|
| `registry_url` | `REGISTRY_URL` | — | Registry base URL (required) |
| `interval` | `HEARTBEAT_INTERVAL` | `60` | Initial heartbeat interval (s); auto-adjusted from server `Retry-After` |
| `a2a_version` | `A2A_VERSION` | `1.0` | A2A format for outgoing heartbeats (`"1.0"` or `"0.3"`) |

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Publishing

```bash
pip install build twine
python -m build
twine upload dist/*
```

## License

MIT
