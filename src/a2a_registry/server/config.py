"""Server-side configuration from environment variables."""

from __future__ import annotations

import os


def get_a2a_version() -> str:
    """Return ``A2A_VERSION`` env var (default ``'1.0'``)."""
    return os.getenv("A2A_VERSION", "1.0")


def get_registry_path() -> str:
    """Return ``REGISTRY_PATH`` env var (default ``'.'``)."""
    return os.getenv("REGISTRY_PATH", ".")
