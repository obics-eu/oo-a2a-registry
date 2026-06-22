"""MCP server extension — exposes registered A2A agent cards as MCP resources."""

from __future__ import annotations

import json
import logging
from urllib.parse import quote, unquote

from mcp import types
from mcp.server import Server
from mcp.server.lowlevel.server import ReadResourceContents
from mcp.server.sse import SseServerTransport
from pydantic import AnyUrl

from fastapi import FastAPI, Request

from .registry import RegistryProvider

logger = logging.getLogger(__name__)

MCP_SSE_PATH = "/mcp/sse"
MCP_POST_PATH = "/mcp/messages"

_AGENTS_URI = "a2a://agents"


def _agent_uri(effective_url: str) -> AnyUrl:
    return AnyUrl(f"{_AGENTS_URI}/{quote(effective_url, safe='')}")


def _url_from_uri(uri: str) -> str:
    prefix = f"{_AGENTS_URI}/"
    return unquote(uri[len(prefix):])


def build_mcp_server(provider: RegistryProvider) -> Server:
    """Return an MCP Server whose resources mirror the live agent registry."""
    server = Server("a2a-registry")

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        agents = await provider.list_available()
        resources: list[types.Resource] = [
            types.Resource(
                uri=AnyUrl(_AGENTS_URI),
                name="Registered A2A Agents",
                description="All currently verified agents in the registry.",
                mimeType="application/json",
            )
        ]
        for card in agents:
            resources.append(
                types.Resource(
                    uri=_agent_uri(card.effective_url),
                    name=card.name,
                    description=card.description or card.effective_url,
                    mimeType="application/json",
                )
            )
        return resources

    @server.list_resource_templates()
    async def list_resource_templates() -> list[types.ResourceTemplate]:
        return [
            types.ResourceTemplate(
                uriTemplate=f"{_AGENTS_URI}/{{url}}",
                name="A2A Agent Card",
                description="Agent card for a specific registered agent (url = percent-encoded agent URL).",
                mimeType="application/json",
            )
        ]

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        uri_str = str(uri)
        agents = await provider.list_available()

        if uri_str == _AGENTS_URI:
            payload = [card.model_dump(exclude_none=True) for card in agents]
            return [ReadResourceContents(
                content=json.dumps(payload, indent=2),
                mime_type="application/json",
            )]

        if uri_str.startswith(f"{_AGENTS_URI}/"):
            target = _url_from_uri(uri_str)
            for card in agents:
                if card.effective_url == target:
                    return [ReadResourceContents(
                        content=card.model_dump_json(exclude_none=True, indent=2),
                        mime_type="application/json",
                    )]
            raise ValueError(f"Agent not found: {target}")

        raise ValueError(f"Unknown resource URI: {uri}")

    return server


def mount_mcp_server(app: FastAPI, provider: RegistryProvider) -> None:
    """Mount MCP SSE endpoints onto an existing FastAPI app.

    Adds:
        GET  /mcp/sse       — SSE stream (MCP client connects here)
        POST /mcp/messages  — JSON-RPC message channel
    """
    mcp = build_mcp_server(provider)
    sse = SseServerTransport(MCP_POST_PATH)

    @app.get(MCP_SSE_PATH, include_in_schema=False)
    async def mcp_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await mcp.run(
                streams[0],
                streams[1],
                mcp.create_initialization_options(),
            )

    @app.post(MCP_POST_PATH, include_in_schema=False)
    async def mcp_messages(request: Request) -> None:
        await sse.handle_post_message(
            request.scope, request.receive, request._send
        )

    logger.info("MCP server mounted at %s (SSE) and %s (POST)", MCP_SSE_PATH, MCP_POST_PATH)
