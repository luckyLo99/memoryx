from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ContextBundle:
    rendered: str
    token_count: int
    truncated: bool = False
    used_summary_fallback: bool = False
    sections: dict[str, list[str]] = field(default_factory=dict)

    # Legacy fields — kept for backward compatibility
    facts: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    lessons: list[str] = field(default_factory=list)
    project_state: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    degraded: bool = False
    total_candidates: int = 0
    token_budget: int = 0

    # New layer fields (24.3B)
    working_context: list[str] = field(default_factory=list)
    policy_context: list[str] = field(default_factory=list)
    session_context: list[str] = field(default_factory=list)
    project_context: list[str] = field(default_factory=list)
    long_term_context: list[str] = field(default_factory=list)
    layer_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "rendered": self.rendered,
            "token_count": self.token_count,
            "truncated": self.truncated,
            "used_summary_fallback": self.used_summary_fallback,
            "sections": self.sections,
            "facts": self.facts,
            "preferences": self.preferences,
            "lessons": self.lessons,
            "project_state": self.project_state,
            "warnings": self.warnings,
            "degraded": self.degraded,
            "total_candidates": self.total_candidates,
            "token_budget": self.token_budget,
            "working_context": self.working_context,
            "policy_context": self.policy_context,
            "session_context": self.session_context,
            "project_context": self.project_context,
            "long_term_context": self.long_term_context,
            "layer_counts": self.layer_counts,
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_prompt_text(self) -> str:
        parts: list[str] = []
        if self.policy_context:
            parts.append("<policy_context>")
            parts.extend(self.policy_context)
            parts.append("</policy_context>")

        if self.working_context:
            parts.append("<working_context>")
            parts.extend(self.working_context)
            parts.append("</working_context>")

        if self.project_context:
            parts.append("<project_context>")
            parts.extend(self.project_context)
            parts.append("</project_context>")

        if self.session_context:
            parts.append("<session_context>")
            parts.extend(self.session_context)
            parts.append("</session_context>")

        if self.long_term_context:
            parts.append("<long_term_context>")
            parts.extend(self.long_term_context)
            parts.append("</long_term_context>")

        if self.rendered:
            parts.append("")
            parts.append("---")
            parts.append("")
            parts.append(self.rendered)

        return "\n".join(parts).strip()
