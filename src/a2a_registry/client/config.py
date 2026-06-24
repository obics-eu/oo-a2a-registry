"""Client-side configuration from environment variables."""

from __future__ import annotations

import os


def get_registry_url() -> str | None:
    """Return ``REGISTRY_URL`` env var, or *None* if not set."""
    return os.getenv("REGISTRY_URL")


def get_a2a_version() -> str:
    """Return ``A2A_VERSION`` env var (default ``'1.0'``)."""
    return os.getenv("A2A_VERSION", "1.0")
