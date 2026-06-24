"""Tests for A2A version conversion, client version-aware sending, and server version-aware responses."""

import pytest
import respx
import httpx

from a2a_registry import RegistryClient, AgentRegistryServer, card_a2a_version, to_v1, to_v03
from a2a_registry.models import HeartbeatRequest
from a2a_registry.server.app import HEARTBEAT_ENDPOINT, AGENTS_ENDPOINT

REGISTRY_URL = "http://registry.example.com"
HEARTBEAT_URL = REGISTRY_URL + HEARTBEAT_ENDPOINT


# ---------------------------------------------------------------------------
# Model conversion
# ---------------------------------------------------------------------------

def test_card_a2a_version_v03(sample_card):
    assert card_a2a_version(sample_card) == "0.3"


def test_card_a2a_version_v1(sample_card_v1):
    assert card_a2a_version(sample_card_v1) == "1.0"


def test_to_v1_from_v03_sets_supported_interfaces(sample_card):
    v1 = to_v1(sample_card)
    assert v1.supportedInterfaces is not None
    assert v1.supportedInterfaces[0].url == sample_card.url
    assert v1.url is None


def test_to_v1_from_v03_preserves_metadata(sample_card):
    v1 = to_v1(sample_card)
    assert v1.name == sample_card.name
    assert v1.description == sample_card.description
    assert v1.capabilities.streaming == sample_card.capabilities.streaming


def test_to_v1_already_v1_returns_same_object(sample_card_v1):
    assert to_v1(sample_card_v1) is sample_card_v1


def test_to_v03_from_v1_sets_top_level_url(sample_card_v1):
    v03 = to_v03(sample_card_v1)
    assert v03.url == sample_card_v1.supportedInterfaces[0].url
    assert v03.supportedInterfaces is None


def test_to_v03_from_v1_preserves_metadata(sample_card_v1):
    v03 = to_v03(sample_card_v1)
    assert v03.name == sample_card_v1.name
    assert v03.description == sample_card_v1.description


def test_to_v03_already_v03_returns_same_object(sample_card):
    assert to_v03(sample_card) is sample_card


def test_to_v1_then_to_v03_roundtrips_url(sample_card):
    assert to_v03(to_v1(sample_card)).url == sample_card.url


def test_to_v03_then_to_v1_roundtrips_url(sample_card_v1):
    original_url = sample_card_v1.supportedInterfaces[0].url
    assert to_v1(to_v03(sample_card_v1)).supportedInterfaces[0].url == original_url


# ---------------------------------------------------------------------------
# Client — version-aware sending
# ---------------------------------------------------------------------------

@respx.mock
async def test_client_converts_v03_card_to_v1_when_configured(sample_card):
    """v0.3 card + a2a_version=1.0 → request body is in v1.0 format."""
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )
    client = RegistryClient(REGISTRY_URL, sample_card, a2a_version="1.0")
    await client.send_once()
    body = HeartbeatRequest.model_validate_json(route.calls[0].request.content)
    assert body.agent_card.supportedInterfaces is not None
    assert body.agent_card.supportedInterfaces[0].url == sample_card.url
    assert body.agent_card.url is None


@respx.mock
async def test_client_keeps_v03_card_as_v03_when_configured(sample_card):
    """v0.3 card + a2a_version=0.3 → request body stays in v0.3 format."""
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )
    client = RegistryClient(REGISTRY_URL, sample_card, a2a_version="0.3")
    await client.send_once()
    body = HeartbeatRequest.model_validate_json(route.calls[0].request.content)
    assert body.agent_card.url == sample_card.url
    assert body.agent_card.supportedInterfaces is None


@respx.mock
async def test_client_converts_v1_card_to_v03_when_configured(sample_card_v1):
    """v1.0 card + a2a_version=0.3 → request body is in v0.3 format."""
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )
    client = RegistryClient(REGISTRY_URL, sample_card_v1, a2a_version="0.3")
    await client.send_once()
    body = HeartbeatRequest.model_validate_json(route.calls[0].request.content)
    assert body.agent_card.url == sample_card_v1.supportedInterfaces[0].url
    assert body.agent_card.supportedInterfaces is None


@respx.mock
async def test_client_keeps_v1_card_as_v1_when_configured(sample_card_v1):
    """v1.0 card + a2a_version=1.0 → request body stays in v1.0 format."""
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )
    client = RegistryClient(REGISTRY_URL, sample_card_v1, a2a_version="1.0")
    await client.send_once()
    body = HeartbeatRequest.model_validate_json(route.calls[0].request.content)
    assert body.agent_card.supportedInterfaces is not None
    assert body.agent_card.url is None


@respx.mock
async def test_client_sends_a2a_version_header_v1(sample_card):
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )
    await RegistryClient(REGISTRY_URL, sample_card, a2a_version="1.0").send_once()
    assert route.calls[0].request.headers.get("A2A-Version") == "1.0"


@respx.mock
async def test_client_sends_a2a_version_header_v03(sample_card):
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )
    await RegistryClient(REGISTRY_URL, sample_card, a2a_version="0.3").send_once()
    assert route.calls[0].request.headers.get("A2A-Version") == "0.3"


def test_client_uses_registry_url_from_env(sample_card, monkeypatch):
    monkeypatch.setenv("REGISTRY_URL", REGISTRY_URL)
    client = RegistryClient(agent_card=sample_card)
    assert client.registry_url == REGISTRY_URL.rstrip("/")


def test_client_raises_without_registry_url(sample_card, monkeypatch):
    monkeypatch.delenv("REGISTRY_URL", raising=False)
    with pytest.raises(ValueError, match="REGISTRY_URL"):
        RegistryClient(agent_card=sample_card)


def test_client_uses_a2a_version_from_env(sample_card, monkeypatch):
    monkeypatch.setenv("A2A_VERSION", "0.3")
    client = RegistryClient(REGISTRY_URL, sample_card)
    assert client.a2a_version == "0.3"


def test_client_explicit_a2a_version_overrides_env(sample_card, monkeypatch):
    monkeypatch.setenv("A2A_VERSION", "0.3")
    client = RegistryClient(REGISTRY_URL, sample_card, a2a_version="1.0")
    assert client.a2a_version == "1.0"


# ---------------------------------------------------------------------------
# Server — version-aware agent list
# ---------------------------------------------------------------------------

def _make_app_client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    )


def _app_with_v03_agent(sample_card):
    """Return (app, respx mock) with sample_card (v0.3) registered and verified."""
    base = sample_card.url.rstrip("/")
    respx.get(base + "/.well-known/agent.json").mock(
        return_value=httpx.Response(200, json=sample_card.model_dump())
    )
    return AgentRegistryServer().create_app()


def _app_with_v1_agent(sample_card_v1):
    base = "http://agent-v1.example.com"
    respx.get(base + "/.well-known/agent-card.json").mock(
        return_value=httpx.Response(200, json=sample_card_v1.model_dump())
    )
    return AgentRegistryServer().create_app()


async def _register(client, card):
    payload = HeartbeatRequest(agent_card=card, interval=30)
    await client.post(
        "/registry/heartbeat",
        content=payload.model_dump_json(),
        headers={"Content-Type": "application/json"},
    )


@respx.mock
async def test_server_returns_v1_format_for_v1_header_stored_v03(sample_card):
    """Stored v0.3 card → A2A-Version: 1.0 header → response in v1.0 format."""
    app = _app_with_v03_agent(sample_card)
    async with _make_app_client(app) as client:
        await _register(client, sample_card)
        resp = await client.get(AGENTS_ENDPOINT, headers={"A2A-Version": "1.0"})
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["supportedInterfaces"] is not None
    assert agents[0]["supportedInterfaces"][0]["url"] == sample_card.url
    assert agents[0]["url"] is None


@respx.mock
async def test_server_returns_v03_format_for_v03_header_stored_v03(sample_card):
    """Stored v0.3 card → A2A-Version: 0.3 header → response in v0.3 format."""
    app = _app_with_v03_agent(sample_card)
    async with _make_app_client(app) as client:
        await _register(client, sample_card)
        resp = await client.get(AGENTS_ENDPOINT, headers={"A2A-Version": "0.3"})
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["url"] == sample_card.url
    assert agents[0]["supportedInterfaces"] is None


@respx.mock
async def test_server_returns_v1_format_for_v1_header_stored_v1(sample_card_v1):
    """Stored v1.0 card → A2A-Version: 1.0 header → response in v1.0 format."""
    app = _app_with_v1_agent(sample_card_v1)
    async with _make_app_client(app) as client:
        await _register(client, sample_card_v1)
        resp = await client.get(AGENTS_ENDPOINT, headers={"A2A-Version": "1.0"})
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["supportedInterfaces"] is not None
    assert agents[0]["url"] is None


@respx.mock
async def test_server_returns_v03_format_for_v03_header_stored_v1(sample_card_v1):
    """Stored v1.0 card → A2A-Version: 0.3 header → response in v0.3 format."""
    app = _app_with_v1_agent(sample_card_v1)
    async with _make_app_client(app) as client:
        await _register(client, sample_card_v1)
        resp = await client.get(AGENTS_ENDPOINT, headers={"A2A-Version": "0.3"})
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["url"] == sample_card_v1.supportedInterfaces[0].url
    assert agents[0]["supportedInterfaces"] is None


@respx.mock
async def test_server_defaults_to_v1_when_no_header(sample_card, monkeypatch):
    """No A2A-Version header + default env (1.0) → response in v1.0 format."""
    monkeypatch.setenv("A2A_VERSION", "1.0")
    app = _app_with_v03_agent(sample_card)
    async with _make_app_client(app) as client:
        await _register(client, sample_card)
        resp = await client.get(AGENTS_ENDPOINT)
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["supportedInterfaces"] is not None


@respx.mock
async def test_server_uses_env_version_when_no_header(sample_card, monkeypatch):
    """No A2A-Version header + A2A_VERSION=0.3 env → response in v0.3 format."""
    monkeypatch.setenv("A2A_VERSION", "0.3")
    app = _app_with_v03_agent(sample_card)
    async with _make_app_client(app) as client:
        await _register(client, sample_card)
        resp = await client.get(AGENTS_ENDPOINT)
    agents = resp.json()
    assert len(agents) == 1
    assert agents[0]["url"] == sample_card.url
