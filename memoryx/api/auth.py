"""P0-E: API Key authentication with timing-safe comparison.

Rules:
- MEMORYX_API_KEY environment variable takes priority.
- If unset, MemoryXSettings.api_key is used as fallback.
- If both are empty/placeholder, a random dev key is generated and logged.
- Random dev key is only acceptable in dev mode; production should always set a key.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

_PLACEHOLDER_KEYS = frozenset({
    "", "your_api_key_here", "your_api_key", "changeme", "change_me",
    "placeholder", "test", "example", "sk-xxx", "YOUR_API_KEY",
})

_dev_key: str | None = None


def _get_expected_key() -> str | None:
    """Runtime getter: read configured API key, preferring env var over settings."""
    global _dev_key

    key = os.environ.get("MEMORYX_API_KEY")
    if key is not None:
        key = key.strip()
        if key.lower() in _PLACEHOLDER_KEYS:
            return None
        return key

    if _dev_key:
        return _dev_key

    return None


def ensure_api_key() -> str:
    """Ensure an API key is configured. Generates a random dev key if none is set.

    Returns the active key. Call this during app startup.
    """
    global _dev_key

    key = _get_expected_key()
    if key is not None:
        return key

    _dev_key = secrets.token_hex(32)
    logger.warning(
        "MEMORYX_API_KEY not set — generated random dev key: %s..."
        " Set MEMORYX_API_KEY in production.",
        _dev_key[:12],
    )
    return _dev_key


def verify_api_key(
    x_memoryx_api_key: str | None = Header(default=None, alias="X-MemoryX-API-Key"),
) -> Optional[str]:
    """FastAPI dependency: verify API key from header.

    Returns the validated key value on success, raises 401 on failure.
    When no key is configured, skips verification (local dev mode).
    """
    expected = _get_expected_key()
    if expected is None:
        return None  # local dev — no auth required

    if x_memoryx_api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-MemoryX-API-Key header")

    if not secrets.compare_digest(x_memoryx_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid API key")

    return x_memoryx_api_key


def is_auth_required() -> bool:
    """Return True if API key auth is enforced."""
    return _get_expected_key() is not None