"""Fuzzy search — Levenshtein + alias expansion for robust query matching.

Exposes
=======
- :func:`expand_query_with_fuzzy_aliases` — alias/typo-correction expansion
  that never raises. If pypinyin is installed, adds pinyin alias too.
- :func:`levenshtein` — minimal, dependency-free edit distance.
- :func:`best_fuzzy_match` — pick best candidate token from a list.

These are designed to be called from the query pipeline when FTS5 returns
zero results.
"""

from __future__ import annotations

from typing import Iterable


# ---------------------------------------------------------------------------
# Alias catalog — curated, static. Never hard-codes a "correction"; it expands
# to additional search tokens (OR), not replacement.
# ---------------------------------------------------------------------------

FUZZY_ALIASES: dict[str, list[str]] = {
    # English typos and common abbreviations
    "dont": ["do not"],
    "cant": ["can not", "cannot"],
    "setup": ["set up"],
    "config": ["configuration", "setting"],
    "settings": ["configuration", "config"],
    "err": ["error"],
    "errors": ["error"],
    "dbg": ["debug"],
    "info": ["information"],
    "repo": ["repository", "project"],
    "repos": ["repository", "project"],
    "dir": ["directory", "folder"],
    "file": ["files"],
    "files": ["file"],
    "func": ["function"],
    "functions": ["function"],
    "args": ["arguments"],
    "argv": ["arguments"],
    "param": ["parameter"],
    "params": ["parameter"],
    "init": ["initialize", "__init__"],
    "lib": ["library"],
    "libs": ["library"],
    "test": ["tests", "testing"],
    "tests": ["test"],
    "dep": ["dependency", "dependencies"],
    "deps": ["dependency", "dependencies"],
    "pkg": ["package"],
    "pkgs": ["package"],
    "prod": ["production"],
    "dev": ["development", "develop"],
    "refactor": ["refactoring", "refactored"],
    "perf": ["performance"],
    "cpu": ["processor", "machine"],
    "api": ["application", "interface"],
    "url": ["link", "address"],
    "db": ["database", "sqlite"],
    "sql": ["query", "database"],
    "redis": ["cache"],
    "docker": ["container"],
    "k8s": ["kubernetes"],
    # Chinese: common informal -> formal aliases (expand only)
    "报错": ["错误", "异常"],
    "错误": ["报错", "异常"],
    "问题": ["issue", "bug", "错误"],
    "bug": ["问题", "错误", "bug"],
    "教程": ["guide", "tutorial", "how to"],
    "指南": ["guide", "tutorial", "教程"],
    "怎么做": ["教程", "步骤", "流程"],
    "怎么弄": ["教程", "步骤", "流程"],
    "如何": ["how", "教程", "方法"],
    "办法": ["solution", "办法", "方法"],
    "解决": ["solution", "fix", "解决"],
    "修复": ["fix", "修复", "解决"],
    "启动": ["start", "run"],
    "停止": ["stop", "停止"],
    "关闭": ["close", "关闭"],
    "打开": ["open"],
    "配置": ["config", "设置", "configuration"],
    "设置": ["config", "配置", "setting"],
    "更新": ["update", "升级"],
    "升级": ["update", "升级"],
    "安装": ["install", "安装"],
    "部署": ["deploy", "部署"],
    "代码": ["code", "代码"],
    "文件": ["file"],
    "项目": ["project"],
    "测试": ["test", "测试"],
    "部署": ["deploy"],
    "数据库": ["database", "db"],
}

# Very common prefix/transformation pairs for short typos:
_TYPO_NORMALIZE: dict[str, str] = {
    "colour": "color",
    "colour": "color",
    "favourite": "favorite",
    "favor": "favor",
    "organi": "organi",  # no-op; real normalization below
}


# ---------------------------------------------------------------------------
# Levenshtein edit distance (minimal implementation, no numpy).
# ---------------------------------------------------------------------------

def levenshtein(a: str, b: str) -> int:
    """Return edit distance between two strings (case-sensitive)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Simple DP. Not designed for very long strings — our inputs are tokens.
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(
                curr[j - 1] + 1,       # insertion
                prev[j] + 1,           # deletion
                prev[j - 1] + cost,    # substitution
            ))
        prev = curr
    return prev[-1]


def normalized_edit_distance(a: str, b: str) -> float:
    """Return levenshtein / max(len) — in ``[0, 1]``, 0 means identical."""
    if not a and not b:
        return 0.0
    if not a or not b:
        return 1.0
    return levenshtein(a, b) / max(len(a), len(b))


def best_fuzzy_match(token: str, candidates: Iterable[str], max_distance: float = 0.33) -> str | None:
    """Return the candidate closest to ``token`` when normalized distance
    is under ``max_distance``, otherwise ``None``.

    ``candidates`` must be the tokens already known (FTS5 vocab or similar).
    """
    if not token:
        return None
    best: tuple[float, str] | None = None
    for candidate in candidates:
        if not candidate:
            continue
        if candidate == token:
            return candidate
        d = normalized_edit_distance(token.lower(), candidate.lower())
        if d <= max_distance:
            if best is None or d < best[0]:
                best = (d, candidate)
    return best[1] if best is not None else None


# ---------------------------------------------------------------------------
# Query expansion: deterministic, stateless.
# ---------------------------------------------------------------------------

def expand_query_with_fuzzy_aliases(tokens: list[str]) -> list[str]:
    """Return the original tokens plus any aliases and light fuzzy expansions.

    - Keeps order and uniqueness (by first-seen position).
    - Never exceeds 32 tokens to avoid exploding FTS5 queries.
    - Safe: no network, no exceptions, no heavy imports.
    """
    if not tokens:
        return []

    seen: set[str] = set()
    out: list[str] = []

    for tok in tokens:
        t = tok.strip().lower()
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            out.append(tok)
        # Static alias expansion
        for alias in FUZZY_ALIASES.get(t, []):
            if alias not in seen:
                seen.add(alias)
                out.append(alias)
        # Typo-normalize — when a token exactly matches an entry in
        # _TYPO_NORMALIZE, append the normalized form.
        nform = _TYPO_NORMALIZE.get(t)
        if nform and nform not in seen:
            seen.add(nform)
            out.append(nform)

    # Optional pinyin expansion when available. Do NOT hard-depend on pypinyin.
    try:
        from pypinyin import lazy_pinyin  # type: ignore
        _has_pinyin = True
    except ImportError:
        _has_pinyin = False

    if _has_pinyin:
        for tok in list(out):
            if any("\u4e00" <= ch <= "\u9fff" for ch in tok):
                pinyin_tokens = lazy_pinyin(tok)
                joined = "".join(pinyin_tokens)
                if joined and joined not in seen and len(out) < 32:
                    seen.add(joined)
                    out.append(joined)
                space = " ".join(pinyin_tokens)
                if space and space not in seen and len(out) < 32:
                    seen.add(space)
                    out.append(space)

    return out[:32]
