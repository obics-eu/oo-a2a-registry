"""Tests for the MCP server extension."""

import json
from urllib.parse import quote

import pytest
from mcp import types

from a2a_registry import AgentRegistryServer
from a2a_registry.models import AgentCard
from a2a_registry.server.mcp_server import (
    MCP_POST_PATH,
    MCP_SSE_PATH,
    _AGENTS_URI,
    _agent_uri,
    _url_from_uri,
    build_mcp_server,
)
from a2a_registry.server.registry import MemoryRegistryProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _populated_provider(card: AgentCard) -> MemoryRegistryProvider:
    provider = MemoryRegistryProvider()
    await provider.upsert(card, interval=60)
    await provider.mark_verified(card.effective_url)
    return provider


async def _list_resources(server):
    handler = server.request_handlers[types.ListResourcesRequest]
    result = await handler(types.ListResourcesRequest(method="resources/list", params=None))
    return result.root.resources


async def _list_templates(server):
    handler = server.request_handlers[types.ListResourceTemplatesRequest]
    result = await handler(
        types.ListResourceTemplatesRequest(method="resources/templates/list", params=None)
    )
    return result.root.resourceTemplates


async def _read_resource(server, uri: str):
    handler = server.request_handlers[types.ReadResourceRequest]
    req = types.ReadResourceRequest(
        method="resources/read",
        params=types.ReadResourceRequestParams(uri=uri),
    )
    result = await handler(req)
    return result.root


# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------

def test_agent_uri_encodes_url(sample_card):
    uri = str(_agent_uri(sample_card.url))
    assert uri == f"a2a://agents/{quote(sample_card.url, safe='')}"


def test_url_from_uri_roundtrips(sample_card):
    uri = str(_agent_uri(sample_card.url))
    assert _url_from_uri(uri) == sample_card.url


def test_agent_uri_v1(sample_card_v1):
    uri = str(_agent_uri(sample_card_v1.effective_url))
    assert _url_from_uri(uri) == sample_card_v1.effective_url


# ---------------------------------------------------------------------------
# list_resources
# ---------------------------------------------------------------------------

async def test_list_resources_empty():
    server = build_mcp_server(MemoryRegistryProvider())
    resources = await _list_resources(server)
    uris = [str(r.uri) for r in resources]
    assert _AGENTS_URI in uris
    assert len(uris) == 1


async def test_list_resources_with_agent(sample_card):
    server = build_mcp_server(await _populated_provider(sample_card))
    resources = await _list_resources(server)
    uris = [str(r.uri) for r in resources]
    assert _AGENTS_URI in uris
    assert str(_agent_uri(sample_card.effective_url)) in uris
    assert len(uris) == 2


async def test_resource_name_matches_agent(sample_card):
    server = build_mcp_server(await _populated_provider(sample_card))
    resources = await _list_resources(server)
    by_uri = {str(r.uri): r for r in resources}
    agent_res = by_uri[str(_agent_uri(sample_card.effective_url))]
    assert agent_res.name == sample_card.name


# ---------------------------------------------------------------------------
# list_resource_templates
# ---------------------------------------------------------------------------

async def test_list_resource_templates():
    server = build_mcp_server(MemoryRegistryProvider())
    templates = await _list_templates(server)
    assert len(templates) == 1
    assert "{url}" in templates[0].uriTemplate


# ---------------------------------------------------------------------------
# read_resource — aggregate
# ---------------------------------------------------------------------------

async def test_read_agents_resource_empty():
    server = build_mcp_server(MemoryRegistryProvider())
    result = await _read_resource(server, _AGENTS_URI)
    assert result.contents[0].mimeType == "application/json"
    assert json.loads(result.contents[0].text) == []


async def test_read_agents_resource_with_agent(sample_card):
    server = build_mcp_server(await _populated_provider(sample_card))
    result = await _read_resource(server, _AGENTS_URI)
    data = json.loads(result.contents[0].text)
    assert len(data) == 1
    assert data[0]["name"] == sample_card.name


# ---------------------------------------------------------------------------
# read_resource — per-agent
# ---------------------------------------------------------------------------

async def test_read_individual_agent_resource(sample_card):
    server = build_mcp_server(await _populated_provider(sample_card))
    result = await _read_resource(server, str(_agent_uri(sample_card.effective_url)))
    card_data = json.loads(result.contents[0].text)
    assert card_data["name"] == sample_card.name
    assert card_data["url"] == sample_card.url


async def test_read_individual_agent_resource_v1(sample_card_v1):
    server = build_mcp_server(await _populated_provider(sample_card_v1))
    result = await _read_resource(server, str(_agent_uri(sample_card_v1.effective_url)))
    card_data = json.loads(result.contents[0].text)
    assert card_data["name"] == sample_card_v1.name


async def test_read_unknown_resource_raises():
    server = build_mcp_server(MemoryRegistryProvider())
    with pytest.raises(Exception):
        await _read_resource(server, "a2a://agents/http%3A%2F%2Fnonexistent")


# ---------------------------------------------------------------------------
# AgentRegistryServer integration
# ---------------------------------------------------------------------------

async def test_mcp_endpoints_mounted_via_create_app():
    server = AgentRegistryServer()
    app = server.create_app(mcp=True)
    routes = {r.path for r in app.routes}
    assert MCP_SSE_PATH in routes
    assert MCP_POST_PATH in routes


async def test_mount_mcp_explicit():
    from fastapi import FastAPI
    server = AgentRegistryServer()
    app = FastAPI()
    server.mount_mcp(app)
    routes = {r.path for r in app.routes}
    assert MCP_SSE_PATH in routes
    assert MCP_POST_PATH in routes


async def test_create_app_without_mcp_has_no_mcp_routes():
    server = AgentRegistryServer()
    app = server.create_app()
    routes = {r.path for r in app.routes}
    assert MCP_SSE_PATH not in routes
    assert MCP_POST_PATH not in routes
