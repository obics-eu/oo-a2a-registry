"""Integration tests for the AgentRegistryServer endpoints."""

import pytest
import respx
import httpx

from a2a_registry import AgentRegistryServer
from a2a_registry.models import AgentCard, AgentInterface, HeartbeatRequest


@pytest.fixture
def server():
    return AgentRegistryServer()


@pytest.fixture
def app(server):
    return server.create_app()


# Helper: async httpx client pointing at the ASGI app
def make_client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


async def test_list_agents_empty(app):
    async with make_client(app) as client:
        resp = await client.get("/.well-known/agents")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# A2A v0.3 tests (top-level url, agent.json discovery)
# ---------------------------------------------------------------------------

@respx.mock
async def test_heartbeat_verifies_agent(app, sample_card):
    # v0.3: server tries agent.json first
    well_known_url = sample_card.url.rstrip("/") + "/.well-known/agent.json"
    respx.get(well_known_url).mock(
        return_value=httpx.Response(200, json=sample_card.model_dump())
    )

    payload = HeartbeatRequest(agent_card=sample_card, interval=30)
    async with make_client(app) as client:
        resp = await client.post(
            "/registry/heartbeat",
            content=payload.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["status"] == "ok"


@respx.mock
async def test_heartbeat_registers_and_lists_agent(app, sample_card):
    well_known_url = sample_card.url.rstrip("/") + "/.well-known/agent.json"
    respx.get(well_known_url).mock(
        return_value=httpx.Response(200, json=sample_card.model_dump())
    )

    payload = HeartbeatRequest(agent_card=sample_card, interval=30)
    async with make_client(app) as client:
        await client.post(
            "/registry/heartbeat",
            content=payload.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        resp = await client.get("/.well-known/agents")

    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["url"] == sample_card.url


@respx.mock
async def test_heartbeat_unreachable_agent_stays_unverified(app, sample_card):
    # Both well-known paths fail
    base = sample_card.url.rstrip("/")
    respx.get(base + "/.well-known/agent.json").mock(return_value=httpx.Response(503))
    respx.get(base + "/.well-known/agent-card.json").mock(return_value=httpx.Response(503))

    payload = HeartbeatRequest(agent_card=sample_card, interval=30)
    async with make_client(app) as client:
        resp = await client.post(
            "/registry/heartbeat",
            content=payload.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        assert resp.json()["verified"] is False

        agents = (await client.get("/.well-known/agents")).json()
    assert agents == []


@respx.mock
async def test_second_heartbeat_skips_refetch(app, sample_card):
    well_known_url = sample_card.url.rstrip("/") + "/.well-known/agent.json"
    route = respx.get(well_known_url).mock(
        return_value=httpx.Response(200, json=sample_card.model_dump())
    )

    payload = HeartbeatRequest(agent_card=sample_card, interval=30)
    async with make_client(app) as client:
        for _ in range(2):
            await client.post(
                "/registry/heartbeat",
                content=payload.model_dump_json(),
                headers={"Content-Type": "application/json"},
            )

    # Remote card fetched exactly once (verified on first heartbeat only)
    assert route.call_count == 1


async def test_setup_mounts_into_existing_app(sample_card):
    from fastapi import FastAPI

    existing_app = FastAPI()

    @existing_app.get("/custom")
    def custom():
        return {"hello": "world"}

    registry = AgentRegistryServer()
    registry.setup(existing_app)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=existing_app),
        base_url="http://test",
    ) as client:
        assert (await client.get("/custom")).status_code == 200
        assert (await client.get("/.well-known/agents")).status_code == 200


# ---------------------------------------------------------------------------
# A2A v1.0 tests (supportedInterfaces, agent-card.json discovery)
# ---------------------------------------------------------------------------

@respx.mock
async def test_v1_heartbeat_verifies_agent(app, sample_card_v1):
    # v1.0: server tries agent-card.json first (origin of supportedInterfaces[0].url)
    base = "http://agent-v1.example.com"
    well_known_url = base + "/.well-known/agent-card.json"
    respx.get(well_known_url).mock(
        return_value=httpx.Response(200, json=sample_card_v1.model_dump())
    )

    payload = HeartbeatRequest(agent_card=sample_card_v1, interval=30)
    async with make_client(app) as client:
        resp = await client.post(
            "/registry/heartbeat",
            content=payload.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["verified"] is True
    assert body["status"] == "ok"


@respx.mock
async def test_v1_heartbeat_registers_and_lists_agent(app, sample_card_v1):
    base = "http://agent-v1.example.com"
    respx.get(base + "/.well-known/agent-card.json").mock(
        return_value=httpx.Response(200, json=sample_card_v1.model_dump())
    )

    payload = HeartbeatRequest(agent_card=sample_card_v1, interval=30)
    async with make_client(app) as client:
        await client.post(
            "/registry/heartbeat",
            content=payload.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
        resp = await client.get("/.well-known/agents")

    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) == 1
    # v1.0 card: url is inside supportedInterfaces, not at top-level
    assert agents[0]["url"] is None
    assert agents[0]["supportedInterfaces"][0]["url"] == sample_card_v1.supportedInterfaces[0].url


@respx.mock
async def test_v1_falls_back_to_agent_json(app, sample_card_v1):
    """v1.0 agent card is at agent.json (legacy hosting) — fallback must succeed."""
    base = "http://agent-v1.example.com"
    respx.get(base + "/.well-known/agent-card.json").mock(return_value=httpx.Response(404))
    respx.get(base + "/.well-known/agent.json").mock(
        return_value=httpx.Response(200, json=sample_card_v1.model_dump())
    )

    payload = HeartbeatRequest(agent_card=sample_card_v1, interval=30)
    async with make_client(app) as client:
        resp = await client.post(
            "/registry/heartbeat",
            content=payload.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
    assert resp.json()["verified"] is True


@respx.mock
async def test_v03_falls_back_to_agent_card_json(app, sample_card):
    """v0.3 agent card is at agent-card.json (v1.0 hosting) — fallback must succeed."""
    base = sample_card.url.rstrip("/")
    respx.get(base + "/.well-known/agent.json").mock(return_value=httpx.Response(404))
    respx.get(base + "/.well-known/agent-card.json").mock(
        return_value=httpx.Response(200, json=sample_card.model_dump())
    )

    payload = HeartbeatRequest(agent_card=sample_card, interval=30)
    async with make_client(app) as client:
        resp = await client.post(
            "/registry/heartbeat",
            content=payload.model_dump_json(),
            headers={"Content-Type": "application/json"},
        )
    assert resp.json()["verified"] is True
