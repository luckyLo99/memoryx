from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContextBudgetPolicy:
    """Deterministic context budget allocation (24.5-B).

    max_tokens: global token budget for rendered context.
    hard_reserve_*: tokens guaranteed for working/warnings/policy.
    min_*/max_*: quota bounds for project/session/long_term.
    evidence_annotation / source_annotation / layer_annotation: toggle annotation.
    summarize_line_limit / summarize_token_limit_per_line: truncation params.
    """
    max_tokens: int = 100_000

    hard_reserve_working: int = 120
    hard_reserve_warnings: int = 120
    hard_reserve_policy: int = 240

    min_project: int = 180
    max_project: int = 300

    min_session: int = 140
    max_session: int = 240

    min_long_term: int = 120
    max_long_term: int = 300

    evidence_annotation: bool = True
    source_annotation: bool = True
    layer_annotation: bool = True

    summarize_line_limit: int = 3
    summarize_token_limit_per_line: int = 8

    @classmethod
    def from_max_token_budget(cls, max_token_budget: int) -> "ContextBudgetPolicy":
        """Build a policy scaled from a legacy max_token_budget value."""
        ratio = max_token_budget / 100000
        return cls(
            max_tokens=max_token_budget,
            hard_reserve_working=max(60, int(120 * ratio)),
            hard_reserve_warnings=max(60, int(120 * ratio)),
            hard_reserve_policy=max(120, int(240 * ratio)),
            min_project=max(60, int(180 * ratio)),
            max_project=max(120, int(300 * ratio)),
            min_session=max(60, int(140 * ratio)),
            max_session=max(120, int(240 * ratio)),
            min_long_term=max(60, int(120 * ratio)),
            max_long_term=max(120, int(300 * ratio)),
        )


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

    # 24.5-B: budget observability
    budget_report: dict = field(default_factory=dict)
    truncation_reason: str | None = None

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
            "budget_report": self.budget_report,
            "truncation_reason": self.truncation_reason,
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
