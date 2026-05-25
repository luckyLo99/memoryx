from __future__ import annotations

import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SkillAtom:
    id: str
    atom_type: str
    intent: str
    summary: str
    raw_excerpt: str
    tags: list[str]
    evidence: list[dict[str, Any]]
    trust_score: float


class MemoryXSkillDistiller:
    """Distill reusable skill drafts from MemoryX/Hermes/Feishu trajectories.

    This intentionally creates draft-only skills. Approval is required before
    installing into Hermes.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def extract_atoms_from_recent_sessions(
        self,
        *,
        since_hours: int = 24,
        min_trust: float = 0.65,
    ) -> list[SkillAtom]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, session_id, content, source_type, verification_status,
                       trust_score, created_at
                FROM memories
                WHERE created_at >= datetime('now', ?)
                  AND COALESCE(trust_score, 0.5) >= ?
                  AND COALESCE(verification_status, 'unverified') != 'contradicted'
                ORDER BY created_at ASC;
                """,
                (f"-{int(since_hours)} hours", float(min_trust)),
            ).fetchall()

        atoms: list[SkillAtom] = []

        for row in rows:
            content = str(row["content"] or "").strip()
            if len(content) < 40:
                continue

            atom_type = self._classify_atom(content)
            if atom_type == "ignore":
                continue

            atom_id = uuid.uuid4().hex
            intent = self._intent_from_content(content)
            summary = self._summarize_heuristic(content)

            atoms.append(
                SkillAtom(
                    id=atom_id,
                    atom_type=atom_type,
                    intent=intent,
                    summary=summary,
                    raw_excerpt=content[:2000],
                    tags=self._tags(content),
                    evidence=[
                        {
                            "memory_id": row["id"],
                            "session_id": row["session_id"],
                            "source_type": row["source_type"],
                            "verification_status": row["verification_status"],
                            "trust_score": row["trust_score"],
                        }
                    ],
                    trust_score=float(row["trust_score"] or 0.5),
                )
            )

        return atoms

    def persist_atoms(self, atoms: list[SkillAtom]) -> int:
        with self._connect() as conn:
            for a in atoms:
                conn.execute(
                    """
                    INSERT INTO skill_atoms(
                        id, atom_type, intent, summary, raw_excerpt,
                        tags_json, evidence_json, trust_score
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        a.id,
                        a.atom_type,
                        a.intent,
                        a.summary,
                        a.raw_excerpt,
                        json.dumps(a.tags, ensure_ascii=False),
                        json.dumps(a.evidence, ensure_ascii=False),
                        a.trust_score,
                    ),
                )
        return len(atoms)

    def route_atoms_to_candidates(self, atoms: list[SkillAtom]) -> int:
        count = 0
        with self._connect() as conn:
            for a in atoms:
                skill_key = self._skill_key(a)
                contribution = self._candidate_contribution(a)
                weight = self._weight(a)

                conn.execute(
                    """
                    INSERT INTO skill_candidates(
                        id, skill_key, atom_id, contribution, weight_score, status
                    ) VALUES (?, ?, ?, ?, ?, 'pending');
                    """,
                    (
                        uuid.uuid4().hex,
                        skill_key,
                        a.id,
                        contribution,
                        weight,
                    ),
                )
                count += 1

        return count

    def build_skill_drafts(
        self,
        *,
        min_weight: float = 10.0,
        max_drafts: int = 5,
    ) -> list[str]:
        draft_ids: list[str] = []

        with self._connect() as conn:
            groups = conn.execute(
                """
                SELECT skill_key, SUM(weight_score) AS total_weight, COUNT(*) AS n
                FROM skill_candidates
                WHERE status='pending'
                GROUP BY skill_key
                HAVING total_weight >= ?
                ORDER BY total_weight DESC
                LIMIT ?;
                """,
                (float(min_weight), int(max_drafts)),
            ).fetchall()

            for g in groups:
                skill_key = g["skill_key"]

                rows = conn.execute(
                    """
                    SELECT c.*, a.intent, a.summary, a.raw_excerpt, a.evidence_json, a.trust_score
                    FROM skill_candidates c
                    JOIN skill_atoms a ON a.id=c.atom_id
                    WHERE c.skill_key=? AND c.status='pending'
                    ORDER BY c.weight_score DESC, c.created_at ASC;
                    """,
                    (skill_key,),
                ).fetchall()

                markdown = self._render_skill_markdown(skill_key=skill_key, rows=rows)

                draft_id = uuid.uuid4().hex
                conn.execute(
                    """
                    INSERT INTO skill_drafts(
                        id, skill_key, title, description, skill_markdown,
                        evidence_json, status, risk_level
                    ) VALUES (?, ?, ?, ?, ?, ?, 'draft', ?);
                    """,
                    (
                        draft_id,
                        skill_key,
                        self._title(skill_key),
                        f"Draft skill distilled from {len(rows)} MemoryX atoms.",
                        markdown,
                        json.dumps([dict(r) for r in rows], ensure_ascii=False, default=str),
                        self._risk_level(rows),
                    ),
                )

                conn.execute(
                    """
                    UPDATE skill_candidates
                    SET status='drafted'
                    WHERE skill_key=? AND status='pending';
                    """,
                    (skill_key,),
                )

                draft_ids.append(draft_id)

        return draft_ids

    def approve_draft(
        self,
        *,
        draft_id: str,
        hermes_skill_dir: str | Path,
    ) -> Path:
        hermes_skill_dir = Path(hermes_skill_dir)

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM skill_drafts WHERE id=?;",
                (draft_id,),
            ).fetchone()

            if not row:
                raise FileNotFoundError(f"skill draft not found: {draft_id}")

            if row["status"] != "draft":
                raise RuntimeError(f"draft status is not draft: {row['status']}")

            skill_key = row["skill_key"]
            out_dir = hermes_skill_dir / skill_key
            out_dir.mkdir(parents=True, exist_ok=True)

            skill_path = out_dir / "SKILL.md"
            skill_path.write_text(row["skill_markdown"], encoding="utf-8")

            conn.execute(
                """
                UPDATE skill_drafts
                SET status='approved',
                    approved_at=CURRENT_TIMESTAMP,
                    installed_path=?
                WHERE id=?;
                """,
                (str(skill_path), draft_id),
            )

        return skill_path

    def _classify_atom(self, content: str) -> str:
        lowered = content.lower()
        if any(x in lowered for x in ["修复", "解决", "bug", "error", "失败", "traceback"]):
            return "fix_pattern"
        if any(x in lowered for x in ["流程", "步骤", "workflow", "runbook", "部署"]):
            return "workflow_pattern"
        if any(x in lowered for x in ["lesson", "教训", "不要", "必须", "避免"]):
            return "lesson_pattern"
        if any(x in lowered for x in ["学习", "掌握", "复盘", "练习"]):
            return "learning_pattern"
        return "ignore"

    def _intent_from_content(self, content: str) -> str:
        text = re.sub(r"\s+", " ", content)
        return text[:120]

    def _summarize_heuristic(self, content: str) -> str:
        text = re.sub(r"\s+", " ", content)
        return text[:240]

    def _tags(self, content: str) -> list[str]:
        tags = []
        rules = {
            "feishu": ["飞书", "feishu"],
            "memoryx": ["memoryx"],
            "hermes": ["hermes"],
            "learning": ["学习", "mastery", "复盘"],
            "debug": ["debug", "trace", "日志"],
            "skill": ["skill", "技能"],
            "xhs": ["小红书", "xhs"],
        }
        lowered = content.lower()
        for tag, keys in rules.items():
            if any(k.lower() in lowered for k in keys):
                tags.append(tag)
        return tags or ["general"]

    def _skill_key(self, atom: SkillAtom) -> str:
        tags = atom.tags
        if "xhs" in tags or "learning" in tags:
            return "xhs-learning-coach"
        if "feishu" in tags:
            return "feishu-runtime-debugger"
        if "memoryx" in tags or "hermes" in tags:
            return "memoryx-hermes-operator"
        return f"memoryx-{atom.atom_type}"

    def _candidate_contribution(self, atom: SkillAtom) -> str:
        return (
            f"- Intent: {atom.intent}\n"
            f"- Summary: {atom.summary}\n"
            f"- Tags: {', '.join(atom.tags)}\n"
            f"- Trust: {atom.trust_score:.2f}\n"
        )

    def _weight(self, atom: SkillAtom) -> float:
        base = 2.0
        if atom.atom_type in {"lesson_pattern", "fix_pattern"}:
            base += 2.0
        if atom.trust_score >= 0.85:
            base += 2.0
        return min(10.0, base)

    def _title(self, skill_key: str) -> str:
        return skill_key.replace("-", " ").title()

    def _risk_level(self, rows: list[sqlite3.Row]) -> str:
        text = "\n".join(str(r["raw_excerpt"]) for r in rows).lower()
        risky = ["delete", "rm -rf", "deploy", "生产", "token", "key", "密码"]
        return "high" if any(x in text for x in risky) else "medium"

    def _render_skill_markdown(self, *, skill_key: str, rows: list[sqlite3.Row]) -> str:
        title = self._title(skill_key)

        evidence_blocks = []
        for r in rows[:12]:
            evidence_blocks.append(
                f"- {r['summary']}  \n"
                f"  Trust: {float(r['trust_score'] or 0.5):.2f}"
            )

        return f"""---
name: {skill_key}
description: Auto-drafted MemoryX skill. Must be reviewed before use.
---

# {title}

## Purpose

This skill was drafted from verified MemoryX/Hermes trajectories. Use it only after human approval.

## When to use

Use this skill when the current task matches the evidence patterns below.

## Evidence Patterns

{chr(10).join(evidence_blocks)}

## Operating Rules

1. Prefer verified user intent and tool evidence over agent self-reflection.
2. If the task touches deployment, deletion, credentials, production data, or external side effects, require dry-run or user confirmation.
3. Do not treat this skill as a fact source. Use MemoryX claim guard for factual claims.
4. Record the outcome back to MemoryX after use.

## Workflow

1. Identify the user's current intent.
2. Match it against the evidence patterns.
3. Apply only the relevant operating rule.
4. Produce a small, verifiable next action.
5. Store success, failure, and user feedback.

## Review Notes

This is a draft generated by MemoryX Skill Distiller. It should be reviewed before installation.
"""