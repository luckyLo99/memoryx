from __future__ import annotations

from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime


CST = ZoneInfo("Asia/Shanghai")


class StudyArtifactBuilder:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
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
        path = self.study_dir / f"{project_id}-session-review.md"
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
        path = self.study_dir / f"{project_id}-mastery-check.md"
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