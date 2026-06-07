from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TokenEstimate:
    """Estimated token count and character info for a text fragment."""
    text_chars: int
    estimated_tokens: int


_CHAR_TO_TOKEN_RATIO = 0.25  # ~4 chars per token for typical text


class TokenEstimator:
    """Lightweight token estimator using character-based heuristics."""

    def truncate_to_tokens(self, text: str, limit: int) -> str:
        """Truncate text to approximately limit tokens, appending ellipsis."""
        if not text or limit <= 0:
            return ""
        max_chars = int(limit / _CHAR_TO_TOKEN_RATIO)
        if len(text) <= max_chars:
            return text
        truncated = text[:max_chars].rsplit(" ", 1)[0] if " " in text[:max_chars] else text[:max_chars]
        return truncated + "\u2026"

    def estimate_text(self, text: str) -> TokenEstimate:
        """Estimate token count for the given text."""
        return TokenEstimate(
            text_chars=len(text),
            estimated_tokens=max(1, int(len(text) * _CHAR_TO_TOKEN_RATIO)),
        )
