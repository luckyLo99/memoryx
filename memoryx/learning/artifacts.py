from __future__ import annotations

import os
import re
from pathlib import Path
from datetime import datetime

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[misc]


def _get_cst_tz():
    """Return the Asia/Shanghai timezone, or fall back to UTC.

    ``ZoneInfo("Asia/Shanghai")`` is not available on all Windows
    configurations and some minimal Linux containers. We degrade to the system
    local timezone so the rest of the module remains importable.
    """
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo("Asia/Shanghai")
    except ZoneInfoNotFoundError:
        return None


CST = _get_cst_tz()


def _configured_artifact_root() -> Path:
    return Path(os.path.realpath(os.getenv("MEMORYX_ARTIFACT_ROOT", os.getenv("MEMORYX_ROOT", "data"))))


def _safe_artifact_root(root: str | Path | None = None) -> Path:
    allowed_root = _configured_artifact_root()
    candidate = allowed_root if root is None else Path(os.path.realpath(os.fspath(root)))
    if os.path.commonpath([str(allowed_root), str(candidate)]) != str(allowed_root):
        raise ValueError("artifact root must be inside the configured MemoryX artifact root")
    return candidate


class StudyArtifactBuilder:
    def __init__(self) -> None:
        self.root = _safe_artifact_root()
        self.study_dir = self.root / "study"
        self.study_dir.mkdir(parents=True, exist_ok=True)

    def append_session_review(
        self,
        *,
        project_id: str,
        topic: str,
        goal: str,
        learned: list[str],
        unclear: list[str],
        mistakes: list[str],
        reusable_methods: list[str],
        next_actions: list[str],
    ) -> Path:
        safe_pid = re.sub(r"[^\w\-.]", "_", project_id)
        path = self.study_dir / f"{safe_pid}-session-review.md"
        now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")

        block = [
            f"\n\n## {now} · {topic}",
            "",
            f"**目标**：{goal}",
            "",
            "### 今天学到的",
            *[f"- {x}" for x in learned],
            "",
            "### 仍然模糊的",
            *[f"- {x}" for x in unclear],
            "",
            "### 错误 / 卡点",
            *[f"- {x}" for x in mistakes],
            "",
            "### 值得复用的方法",
            *[f"- {x}" for x in reusable_methods],
            "",
            "### 下一步",
            *[f"- {x}" for x in next_actions],
            "",
        ]

        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(block))

        return path

    def append_mastery_check(
        self,
        *,
        project_id: str,
        topic: str,
        level: str,
        evidence: list[str],
        weak_points: list[str],
        next_tasks: list[str],
    ) -> Path:
        safe_pid = re.sub(r"[^\w\-.]", "_", project_id)
        path = self.study_dir / f"{safe_pid}-mastery-check.md"
        now = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S CST")

        block = [
            f"\n\n## {now} · {topic}",
            "",
            f"**当前掌握等级**：{level}",
            "",
            "### 证据",
            *[f"- {x}" for x in evidence],
            "",
            "### 薄弱点",
            *[f"- {x}" for x in weak_points],
            "",
            "### 下一轮复测任务",
            *[f"- {x}" for x in next_tasks],
            "",
        ]

        with path.open("a", encoding="utf-8") as f:
            f.write("\n".join(block))

        return path
