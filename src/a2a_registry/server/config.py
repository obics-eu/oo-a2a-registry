"""Server-side configuration from environment variables."""

from __future__ import annotations

import os


def get_a2a_version() -> str:
    """Return ``A2A_VERSION`` env var (default ``'1.0'``)."""
    return os.getenv("A2A_VERSION", "1.0")


def get_expected_heartbeat_interval() -> int:
    """Return ``EXPECTED_HEARTBEAT_INTERVAL`` env var in seconds (default 60)."""
    return int(os.getenv("EXPECTED_HEARTBEAT_INTERVAL", "60"))


def get_stale_multiplier() -> int:
    """Return ``STALE_MULTIPLIER`` env var (default 3)."""
    return int(os.getenv("STALE_MULTIPLIER", "3"))


def get_fetch_timeout() -> float:
    """Return ``FETCH_TIMEOUT`` env var in seconds (default 10.0)."""
    return float(os.getenv("FETCH_TIMEOUT", "10.0"))


def get_registry_path() -> str:
    """Return ``REGISTRY_PATH`` env var (default ``'.'``)."""
    return os.getenv("REGISTRY_PATH", ".")
