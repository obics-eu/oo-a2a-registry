"""Tests for the RegistryClient heartbeat logic."""

import asyncio

import pytest
import respx
import httpx

from a2a_registry import RegistryClient
from a2a_registry.models import HeartbeatRequest, HeartbeatResponse
from a2a_registry.server.app import HEARTBEAT_ENDPOINT

REGISTRY_URL = "http://registry.example.com"
HEARTBEAT_URL = REGISTRY_URL + HEARTBEAT_ENDPOINT


@respx.mock
async def test_send_once_success(sample_card):
    respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )

    client = RegistryClient(REGISTRY_URL, sample_card, interval=30)
    result = await client.send_once()

    assert result is not None
    assert result.verified is True
    assert result.status == "ok"


@respx.mock
async def test_send_once_failure_returns_none(sample_card):
    respx.post(HEARTBEAT_URL).mock(return_value=httpx.Response(500))

    client = RegistryClient(REGISTRY_URL, sample_card, interval=30)
    result = await client.send_once()
    assert result is None


@respx.mock
async def test_send_once_posts_correct_payload(sample_card):
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )

    client = RegistryClient(REGISTRY_URL, sample_card, interval=45, a2a_version="0.3")
    await client.send_once()

    assert route.called
    body = HeartbeatRequest.model_validate_json(route.calls[0].request.content)
    assert body.interval == 45
    assert body.agent_card.url == sample_card.url


@respx.mock
async def test_context_manager_starts_and_stops(sample_card):
    respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )

    async with RegistryClient(REGISTRY_URL, sample_card, interval=3600) as c:
        assert c._task is not None
        assert not c._task.done()

    # After exit the task should be cancelled/done
    assert c._task.done()


@respx.mock
async def test_heartbeat_loop_sends_multiple_times(sample_card):
    route = respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )

    # Patch sleep so the loop spins without actually waiting
    call_count = 0

    async def fast_sleep(_):
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            raise asyncio.CancelledError  # stop after 3 sleeps

    client = RegistryClient(REGISTRY_URL, sample_card, interval=60)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(asyncio, "sleep", fast_sleep)
        await client.start()
        try:
            await client._task
        except asyncio.CancelledError:
            pass

    assert route.call_count >= 2


@respx.mock
async def test_send_once_adjusts_interval_from_retry_after(sample_card):
    """Client updates self.interval when server responds with Retry-After."""
    respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(
            202,
            json={"status": "ok", "verified": True},
            headers={"Retry-After": "120"},
        )
    )
    client = RegistryClient(REGISTRY_URL, sample_card, interval=60)
    await client.send_once()
    assert client.interval == 120


@respx.mock
async def test_send_once_keeps_interval_without_retry_after(sample_card):
    """Interval is unchanged when no Retry-After header is returned."""
    respx.post(HEARTBEAT_URL).mock(
        return_value=httpx.Response(200, json={"status": "ok", "verified": True})
    )
    client = RegistryClient(REGISTRY_URL, sample_card, interval=60)
    await client.send_once()
    assert client.interval == 60


def test_client_uses_heartbeat_interval_from_env(sample_card, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_INTERVAL", "45")
    client = RegistryClient(REGISTRY_URL, sample_card)
    assert client.interval == 45


def test_client_explicit_interval_overrides_env(sample_card, monkeypatch):
    monkeypatch.setenv("HEARTBEAT_INTERVAL", "45")
    client = RegistryClient(REGISTRY_URL, sample_card, interval=30)
    assert client.interval == 30
