"""Procedural memory: episodic-to-procedure conversion and skill acquisition.

Transforms repeated episodic patterns into procedural knowledge.

References:
- Squire & Zola (1996). Structure and function of declarative and nondeclarative memory systems.
- Doyon et al. (2009). Contributions of the basal ganglia and functionally related brain structures.
- Anderson (1982). Acquisition of cognitive skill.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProceduralSkill:
    skill_id: str = ""
    name: str = ""
    pattern: str = ""
    frequency: int = 1
    confidence: float = 0.5
    execution_count: int = 0
    source_episodes: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    trigger_keywords: list[str] = field(default_factory=list)


class ProceduralMemory:
    def __init__(self):
        self.skills: dict[str, ProceduralSkill] = {}

    def extract_pattern(self, episodes: list[dict[str, Any]]) -> list[ProceduralSkill]:
        patterns: list[ProceduralSkill] = []
        action_counts: Counter = Counter()
        for ep in episodes:
            action = str(ep.get("action", ep.get("content", "")))
            action_counts[action] += 1
        for action, count in action_counts.most_common(10):
            if count >= 2:
                sid = f"skill_{len(self.skills) + len(patterns) + 1}"
                kw = [w.lower().strip(".,!?") for w in action.split()[:3]]
                s = ProceduralSkill(
                    skill_id=sid, name=f"Pattern: {action[:40]}...",
                    pattern=action, frequency=count,
                    confidence=min(1.0, count * 0.2),
                    trigger_keywords=kw,
                )
                patterns.append(s)
                self.skills[sid] = s
        return patterns

    def execute(self, skill_id: str, context: dict | None = None) -> dict[str, Any]:
        s = self.skills.get(skill_id)
        if s is None:
            return {"ok": False, "error": "Skill not found"}
        s.execution_count += 1
        return {"ok": True, "skill_id": skill_id, "pattern": s.pattern, "execution_count": s.execution_count}

    def match_trigger(self, query: str) -> ProceduralSkill | None:
        q = query.lower()
        best: ProceduralSkill | None = None
        best_score = 0
        for s in self.skills.values():
            score = sum(1 for kw in s.trigger_keywords if kw in q)
            if score > best_score:
                best_score = score
                best = s
        return best

    def clear(self) -> None:
        self.skills.clear()

    def skill_count(self) -> int:
        return len(self.skills)
