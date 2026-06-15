"""FTS5 query utilities — extracted from repository.py to reduce file size.

Provides deterministic tokenization, query building, and alias expansion
for FTS5 full-text search.
"""

from __future__ import annotations

import re as _re

_QUERY_ALIASES: dict[str, list[str]] = {
    "pytest": ["py test", "python test"],
    "rust": ["rust programming", "rust language"],
    "js": ["javascript"],
    "ts": ["typescript"],
    "sqlite": ["sqlite3", "fts5"],
    "db": ["database"],
    "deploy": ["release", "deployment"],
    "build": ["compile"],
}


def tokenize_query_terms(query: str) -> list[str]:
    """Deterministic query tokenizer for FTS5 searches.

    Supports camelCase, snake_case, kebab-case, path, version numbers, and
    produces 2-char (CJK bigram) tokens for Chinese/Japanese/Korean text so
    contiguous Chinese content can still be matched (24.4-C / stability-improved).
    Original words are preserved alongside split forms.
    """
    if not query or not query.strip():
        return []
    raw = query.strip()
    segments = _re.split(r"[-_.\\/\s]", raw)
    tokens: list[str] = []
    for seg in segments:
        if not seg:
            continue
        has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in seg)
        if has_cjk:
            sub_parts = _re.split(r"([\u4e00-\u9fff]+)", seg)
            for sub in sub_parts:
                if not sub:
                    continue
                if all("\u4e00" <= ch <= "\u9fff" for ch in sub):
                    for i in range(len(sub)):
                        ch = sub[i]
                        if ch not in tokens:
                            tokens.append(ch)
                        if i + 1 < len(sub):
                            bigram = sub[i : i + 2]
                            if bigram not in tokens:
                                tokens.append(bigram)
                else:
                    cased = _re.sub(r"([a-z])([A-Z])", r"\1 \2", sub).lower().split()
                    for p in cased:
                        cleaned = _re.sub(r"[^a-z0-9]+", "", p)
                        if cleaned and cleaned not in tokens:
                            tokens.append(cleaned)
        else:
            parts = _re.sub(r"([a-z])([A-Z])", r"\1 \2", seg).lower().split()
            for p in parts:
                p = _re.sub(r"[^a-z0-9]+", "", p)
                if p and p not in tokens:
                    tokens.append(p)
    return tokens[:24]


def build_fts_query(tokens: list[str], operator: str = "AND") -> str:
    """Build a safe FTS5 MATCH query from tokens. Returns empty string if no safe tokens."""
    safe = [t.replace('"', '""') for t in tokens if t]
    if not safe:
        return ""
    if operator == "AND":
        return " AND ".join(safe)
    elif operator == "OR":
        return " OR ".join(safe)
    elif operator == "PHRASE":
        return '"' + safe[0] + '"' if len(safe) == 1 else " NEAR/0 ".join(safe)
    return " OR ".join(safe)


def expand_with_aliases(tokens: list[str]) -> list[str]:
    """Expand tokens using static alias map. Returns up to 16 unique tokens."""
    expanded = list(tokens)
    for t in tokens:
        for alias in _QUERY_ALIASES.get(t, []):
            for sub in alias.split():
                if sub and sub not in expanded:
                    expanded.append(sub)
    return expanded[:16]