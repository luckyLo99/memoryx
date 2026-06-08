from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"
MEMORYX_PATH_REDACTION = "$MEMORYX_HOME/[REDACTED_PATH]"

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "passwd",
    "secret",
    "authorization",
    "cookie",
    "openai_api_key",
    "siliconflow_api_key",
}

_KEY_PATTERN = re.compile(
    r"(?i)\b(openai_api_key|siliconflow_api_key|api_key|apikey|access_token|refresh_token|token|password|passwd|secret|authorization|cookie)\b\s*[:=]\s*(?:Bearer\s+)?[^\s,;\]\}\)\"']+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+\-/=]+")
_MEMORYX_PATH_PATTERN = re.compile(r"/home/[^/]+/\.memoryx(?:/[^\s,;\]\}\)\"']*)?")
_ENV_PATH_PATTERN = re.compile(r"(?i)(?:^|[\s:=])([^\s,;\]\}\)\"']*\.env)(?=$|[\s,;\]\}\)\"'])")


def hash_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:16]


def _redact_key_value(match: re.Match[str]) -> str:
    raw = match.group(0)
    separator = ":" if ":" in raw.split()[0:2] else "="
    key_match = re.match(r"(?i)\b([^\s:=]+)", raw)
    key = key_match.group(1) if key_match else "secret"
    actual_separator = ":" if ":" in raw[: raw.find(key) + len(key) + 3] else separator
    return f"{key}{actual_separator}{REDACTED}"


def redact_text(text: str) -> str:
    if text is None:
        return ""
    redacted = str(text)
    redacted = _MEMORYX_PATH_PATTERN.sub(MEMORYX_PATH_REDACTION, redacted)
    redacted = _ENV_PATH_PATTERN.sub(lambda m: m.group(0).replace(m.group(1), ".env.[REDACTED]"), redacted)
    redacted = _KEY_PATTERN.sub(_redact_key_value, redacted)
    redacted = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", redacted)
    return redacted


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in SENSITIVE_KEYS or any(part in normalized for part in ("api_key", "token", "password", "secret"))


def redact_mapping(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_sensitive_key(key):
                result[key] = REDACTED
            else:
                result[key] = redact_mapping(item)
        return result
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_mapping(item) for item in value]
    return value
