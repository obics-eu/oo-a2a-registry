"""Tests for the in-memory RegistryProvider."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from a2a_registry.models import AgentCard, AgentStatus, RegistryEntry
from a2a_registry.server.registry import MemoryRegistryProvider


# ---------------------------------------------------------------------------
# A2A v0.3 tests (top-level url field)
# ---------------------------------------------------------------------------

async def test_upsert_creates_entry(sample_card):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card, interval=60)
    entry = await provider.get(sample_card.url)
    assert entry is not None
    assert entry.status == AgentStatus.unverified
    assert entry.interval == 60


async def test_upsert_refreshes_timestamp(sample_card):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card, interval=60)
    first = (await provider.get(sample_card.url)).last_heartbeat

    await asyncio.sleep(0.01)
    await provider.upsert(sample_card, interval=60)
    second = (await provider.get(sample_card.url)).last_heartbeat

    assert second >= first


async def test_mark_verified(sample_card):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card, interval=60)
    await provider.mark_verified(sample_card.url)
    entry = await provider.get(sample_card.url)
    assert entry.status == AgentStatus.available


async def test_list_available_only_returns_verified(sample_card):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card, interval=60)

    # unverified agent must not appear
    assert await provider.list_available() == []

    await provider.mark_verified(sample_card.url)
    cards = await provider.list_available()
    assert len(cards) == 1
    assert cards[0].url == sample_card.url


async def test_unregister_removes_entry(sample_card):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card, interval=60)
    await provider.unregister(sample_card.url)
    assert await provider.get(sample_card.url) is None


async def test_get_stale(sample_card):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card, interval=10)

    # Backdate the heartbeat to trigger stale detection (3 × 10s = 30s ago)
    entry = provider._store[sample_card.url]
    entry.last_heartbeat = datetime.now(tz=timezone.utc) - timedelta(seconds=31)

    stale = await provider.get_stale(multiplier=3)
    assert sample_card.url in stale


async def test_fresh_agent_not_stale(sample_card):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card, interval=60)
    stale = await provider.get_stale(multiplier=3)
    assert stale == []


# ---------------------------------------------------------------------------
# A2A v1.0 tests (supportedInterfaces, no top-level url)
# ---------------------------------------------------------------------------

async def test_v1_upsert_creates_entry(sample_card_v1):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card_v1, interval=60)
    # effective_url = supportedInterfaces[0].url
    entry = await provider.get(sample_card_v1.effective_url)
    assert entry is not None
    assert entry.status == AgentStatus.unverified


async def test_v1_mark_verified(sample_card_v1):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card_v1, interval=60)
    await provider.mark_verified(sample_card_v1.effective_url)
    entry = await provider.get(sample_card_v1.effective_url)
    assert entry.status == AgentStatus.available


async def test_v1_list_available(sample_card_v1):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card_v1, interval=60)
    await provider.mark_verified(sample_card_v1.effective_url)
    cards = await provider.list_available()
    assert len(cards) == 1
    assert cards[0].supportedInterfaces[0].url == sample_card_v1.supportedInterfaces[0].url


async def test_v1_unregister(sample_card_v1):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card_v1, interval=60)
    await provider.unregister(sample_card_v1.effective_url)
    assert await provider.get(sample_card_v1.effective_url) is None


async def test_v1_get_stale(sample_card_v1):
    provider = MemoryRegistryProvider()
    await provider.upsert(sample_card_v1, interval=10)

    entry = provider._store[sample_card_v1.effective_url]
    entry.last_heartbeat = datetime.now(tz=timezone.utc) - timedelta(seconds=31)

    stale = await provider.get_stale(multiplier=3)
    assert sample_card_v1.effective_url in stale
