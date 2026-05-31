from __future__ import annotations

import json
from memoryx.retrieval import RetrievalResult
from memoryx.routing import RoutePlan

from .models import ContextBundle, ContextBudgetPolicy


def _resolve_layer_from_result(result: RetrievalResult) -> str:
    """Extract memory_layer from a RetrievalResult's metadata_json if present."""
    raw = getattr(result, "metadata_json", "{}") or "{}"
    try:
        meta = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        meta = {}
    return meta.get("memory_layer", "")


def _is_result_lesson(result: RetrievalResult) -> bool:
    """Check if a retrieval result is a LESSON."""
    if result.memory_type == "LESSON":
        return True
    raw = getattr(result, "metadata_json", "{}") or "{}"
    try:
        meta = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        meta = {}
    return meta.get("memory_class") == "lesson"


# === 24.5-C: compression priority by evidence_level ===================================
# Evidence rank: E4 > E3 > E2 > E1 > E0 > unknown
# Same evidence → higher final_score wins.
# This sort key is used before compression/truncation to retain high-evidence items.
_EVIDENCE_RANK: dict[str, int] = {"E4": 5, "E3": 4, "E2": 3, "E1": 2, "E0": 1}


def _compress_priority_key(result: RetrievalResult) -> tuple[int, float]:
    """Sort key: (evidence_rank, final_score) — higher is better.

    Used by compression/truncation to prioritise high-evidence items.
    Unknown / missing evidence ranks last (0).
    Does NOT change retrieval final_score — only affects which items survive truncation.
    """
    ev = getattr(result, "evidence_level", None)
    if not ev:
        raw = getattr(result, "metadata_json", "{}") or "{}"
        try:
            meta = json.loads(raw) if raw else {}
        except (json.JSONDecodeError, ValueError):
            meta = {}
        ev = meta.get("evidence_level")
    ev_str = str(ev).upper() if ev else ""
    rank = _EVIDENCE_RANK.get(ev_str, 0)
    score = getattr(result, "final_score", 0.0)
    return (rank, score)


def _annotate_line(result: RetrievalResult, *, evidence: bool, source: bool, layer: bool) -> str:
    """Add evidence/source/layer annotation to a memory line (24.5-B)."""
    parts = [f"- ({result.memory_id}) {result.content}"]
    tags = []
    if evidence:
        ev = getattr(result, "evidence_level", None) or "unknown"
        tags.append(f"evidence={ev}")
    if source:
        stype = getattr(result, "source_type", None) or "unknown"
        tags.append(f"source={stype}")
    if layer:
        lyr = _resolve_layer_from_result(result) or "legacy"
        tags.append(f"layer={lyr}")
    if tags:
        parts.append(" [" + " ".join(tags) + "]")
    return "".join(parts)


class ContextAssemblyEngine:
    def __init__(self, max_token_budget: int = 1200, policy: ContextBudgetPolicy | None = None) -> None:
        self.max_token_budget = max_token_budget
        self.policy = policy or ContextBudgetPolicy.from_max_token_budget(max_token_budget)

    def assemble(
        self,
        *,
        system_prompt: str,
        soul_prompt: str,
        current_task: str,
        route_plan: RoutePlan,
        recent_conversation: list[str],
        progressive: bool = False,
        working_context: list[str] | None = None,
        include_lessons: bool = True,
        open_conflicts: list[str] | None = None,
    ) -> ContextBundle:
        policy = self.policy
        deduped = self._deduplicate(route_plan.results)
        # Filter lessons when include_lessons=False
        if not include_lessons:
            deduped = [r for r in deduped if not _is_result_lesson(r)]
        if progressive:
            deduped = self._auto_page(deduped)
        grouped = self._group_memories_by_layer(deduped, progressive=progressive)

        # Annotate lines if policy says so
        if policy.evidence_annotation or policy.source_annotation or policy.layer_annotation:
            annotated_grouped = {}
            for key, lines in grouped.items():
                annotated_grouped[key] = self._annotate_lines(
                    deduped, lines, key,
                    evidence=policy.evidence_annotation,
                    source=policy.source_annotation,
                    layer=policy.layer_annotation,
                )
            grouped = annotated_grouped

        wc = working_context or []
        oc = open_conflicts or []
        warnings_lines = list(oc)

        # Build ordered sections with quota info
        section_specs: list[dict] = [
            {"title": "System Prompt", "lines": [system_prompt], "quota": 9999, "hard": False, "key": "system"},
            {"title": "SOUL", "lines": [soul_prompt], "quota": 9999, "hard": False, "key": "soul"},
            {"title": "Current Task", "lines": [current_task], "quota": 9999, "hard": False, "key": "task"},
            {"title": "Working Context", "lines": wc, "quota": policy.hard_reserve_working, "hard": True, "key": "working_context"},
            {"title": "Warnings", "lines": warnings_lines, "quota": policy.hard_reserve_warnings, "hard": True, "key": "warnings"},
            {"title": "Policy / Guard", "lines": grouped.get("policy", []), "quota": policy.hard_reserve_policy, "hard": True, "key": "policy_context"},
            {"title": "Project Context", "lines": grouped.get("project", []), "quota": policy.max_project, "hard": False, "key": "project_context"},
            {"title": "Session Memory", "lines": grouped.get("session", []), "quota": policy.max_session, "hard": False, "key": "session_context"},
            {"title": "Relevant Long-Term Memory", "lines": grouped.get("long_term", []), "quota": policy.max_long_term, "hard": False, "key": "long_term"},
            {"title": "User Preferences", "lines": grouped.get("user", []), "quota": policy.max_long_term, "hard": False, "key": "user"},
            {"title": "Lessons", "lines": grouped.get("lessons", []), "quota": policy.max_long_term, "hard": False, "key": "lessons"},
            {"title": "Relevant Episodes", "lines": grouped.get("episodic", []), "quota": policy.max_long_term, "hard": False, "key": "episodic"},
            {"title": "Recent Conversation", "lines": recent_conversation, "quota": 9999, "hard": False, "key": "recent"},
        ]

        rendered, token_count, trunc_reason, budget_report, section_map = self._render_with_budget_policy(
            section_specs, policy=policy,
        )

        # Build layer counts
        layer_counts: dict[str, int] = {}
        for layer_key in ("policy", "project", "session", "long_term", "user", "lessons", "episodic"):
            cnt = len(grouped.get(layer_key, []))
            if cnt > 0:
                layer_counts[layer_key] = cnt

        return ContextBundle(
            rendered=rendered,
            token_count=token_count,
            truncated=trunc_reason is not None,
            used_summary_fallback=any(s.get("summarized") for s in budget_report.get("sections", {}).values()),
            sections=section_map,
            # Legacy fields
            facts=grouped.get("long_term", []),
            preferences=grouped.get("user", []),
            lessons=grouped.get("lessons", []),
            project_state=grouped.get("project", []),
            warnings=warnings_lines,
            degraded=False,
            total_candidates=0,
            token_budget=policy.max_tokens,
            # Layer fields
            working_context=wc,
            policy_context=grouped.get("policy", []),
            session_context=grouped.get("session", []),
            project_context=grouped.get("project", []),
            long_term_context=grouped.get("long_term", []) + grouped.get("user", []) + grouped.get("lessons", []),
            layer_counts=layer_counts,
            # 24.5-B budget observability
            budget_report=budget_report,
            truncation_reason=trunc_reason,
        )

    def _render_with_budget_policy(
        self, section_specs: list[dict], *, policy: ContextBudgetPolicy,
    ) -> tuple[str, int, str | None, dict, dict[str, list[str]]]:
        """Render sections with quota-based budget allocation (24.5-B)."""
        max_tokens = policy.max_tokens
        used = 0
        section_map: dict[str, list[str]] = {}
        report_sections: dict[str, dict] = {}
        trunc_reason: str | None = None
        parts: list[str] = []

        for spec in section_specs:
            title = spec["title"]
            lines = spec["lines"]
            quota = spec["quota"]
            hard = spec["hard"]
            key = spec["key"]

            available = min(quota, max_tokens - used)
            if available <= 0:
                # Still try to summarize if section has content and summary fits globally
                if lines:
                    summarized = self._summarize_lines(lines, policy=policy)
                    sum_est = self._token_count("\n".join(summarized))
                    if sum_est > 0 and sum_est <= max_tokens and summarized != lines:
                        # Summary fits in global budget - allow small overflow
                        chosen = summarized
                        sec_text = f"[{title}]\n" + "\n".join(chosen) + "\n"
                        sec_tokens = self._token_count(sec_text)
                        section_map[title] = chosen
                        used += sec_tokens
                        report_sections[key] = {
                            "allocated": 0,
                            "used": sec_tokens,
                            "truncated": False,
                            "summarized": True,
                        }
                        parts.append(f"[{title}]")
                        parts.extend(chosen)
                        parts.append("")
                        continue
                if trunc_reason is None:
                    trunc_reason = f"{key}_exhausted"
                section_map[title] = []
                report_sections[key] = {"allocated": 0, "used": 0, "truncated": True}
                continue

            chosen = list(lines)
            est = self._token_count("\n".join(chosen))

            report_sections[key] = {
                "allocated": available,
                "used": 0,
                "truncated": False,
                "summarized": False,
            }

            if est > available:
                # Try summarize first, then truncate
                summarized = self._summarize_lines(chosen, policy=policy)
                sum_est = self._token_count("\n".join(summarized))
                if sum_est <= available and summarized != chosen:
                    chosen = summarized
                    report_sections[key]["summarized"] = True
                else:
                    chosen = self._fit_lines_to_budget(chosen, available)
                if len(chosen) < len(lines):
                    if trunc_reason is None:
                        trunc_reason = f"{key}_truncated"

            section_map[title] = chosen
            sec_text = f"[{title}]\n" + "\n".join(chosen) + "\n"
            sec_tokens = self._token_count(sec_text)
            used += sec_tokens

            report_sections[key]["used"] = sec_tokens
            report_sections[key]["truncated"] = len(chosen) < len(lines)

            parts.append(f"[{title}]")
            parts.extend(chosen)
            parts.append("")

        rendered = "\n".join(parts).strip() + "\n"
        token_count = self._token_count(rendered)
        if token_count > max_tokens:
            trunc_reason = "global_overflow"
            rendered = " ".join(rendered.split()[:max_tokens])
            token_count = self._token_count(rendered)

        budget_report = {
            "max_tokens": max_tokens,
            "used": used,
            "sections": report_sections,
        }
        return rendered, token_count, trunc_reason, budget_report, section_map

    def _fit_lines_to_budget(self, lines: list[str], budget: int) -> list[str]:
        """Fit lines to a token budget."""
        kept: list[str] = []
        total = 0
        for line in lines:
            cost = self._token_count(line)
            if total + cost > budget:
                break
            kept.append(line)
            total += cost
        return kept

    def _annotate_lines(
        self, results: list[RetrievalResult], lines: list[str], group_key: str,
        *, evidence: bool, source: bool, layer: bool,
    ) -> list[str]:
        """Add evidence/source/layer tags to lines based on matching results."""
        # Build lookup from content snippet to result
        result_map: dict[str, RetrievalResult] = {}
        for r in results:
            snippet = r.content.strip()[:80].lower()
            result_map[snippet] = r

        annotated: list[str] = []
        for line in lines:
            matched = None
            for snippet, r in result_map.items():
                if snippet in line.lower():
                    matched = r
                    break
            if matched:
                annotated.append(_annotate_line(matched, evidence=evidence, source=source, layer=layer))
            else:
                annotated.append(line)
        return annotated

    def _deduplicate(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        seen: set[str] = set()
        deduped: list[RetrievalResult] = []
        for result in sorted(results, key=lambda item: item.final_score, reverse=True):
            normalized = result.content.strip().lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(result)
        return deduped

    def _group_memories_by_layer(self, results: list[RetrievalResult], progressive: bool = False) -> dict[str, list[str]]:
        """Group retrieval results by memory_layer.

        Results are sorted by compression priority (evidence_level → final_score)
        before formatting, so that truncation keeps high-evidence items first.
        """
        # 24.5-C: sort by evidence priority so compression/truncation favours high-evidence items
        ordered = sorted(results, key=_compress_priority_key, reverse=True)
        grouped = {
            "policy": [],
            "project": [],
            "session": [],
            "long_term": [],
            "user": [],
            "lessons": [],
            "episodic": [],
        }
        for result in ordered:
            layer = _resolve_layer_from_result(result)
            if progressive:
                line = f"- [{result.memory_id}] ({result.memory_type}, scope={result.scope}, layer={layer or 'legacy'}, score={result.final_score:.2f})"
            else:
                line = f"- ({result.memory_id}) {result.content}"

            # Layer-based grouping
            if layer in ("policy", "guard"):
                grouped["policy"].append(line)
            elif layer == "project":
                grouped["project"].append(line)
            elif layer == "session":
                grouped["session"].append(line)
            elif layer in ("long_term", ""):
                # Long-term: further split into project, user/preferences, lessons, and general facts
                if result.memory_type in ("PROJECT", "TASK") or result.scope == "project":
                    grouped["project"].append(line)
                elif result.memory_type == "PREFERENCE" or result.scope == "user":
                    grouped["user"].append(line)
                elif result.memory_type == "LESSON":
                    grouped["lessons"].append(line)
                elif result.memory_type == "EPISODIC":
                    grouped["episodic"].append(line)
                else:
                    grouped["long_term"].append(line)
            elif result.memory_type == "EPISODIC":
                grouped["episodic"].append(line)
            else:
                # Fallback: old behaviour
                if result.scope == "user" or result.memory_type == "PREFERENCE":
                    grouped["user"].append(line)
                elif result.memory_type == "LESSON":
                    grouped["lessons"].append(line)
                elif result.scope == "project":
                    grouped["project"].append(line)
                elif result.memory_type == "EPISODIC":
                    grouped["episodic"].append(line)
                else:
                    grouped["long_term"].append(line)

        return grouped

    def _render_with_budget(self, sections: list[tuple[str, list[str]]]) -> tuple[str, int, bool, bool, dict[str, list[str]]]:
        used_summary_fallback = False
        truncated = False
        parts: list[str] = []
        section_map: dict[str, list[str]] = {}

        for title, lines in sections:
            chosen_lines = list(lines)
            if lines and not self._fits(parts, title, chosen_lines):
                summarized = self._summarize_lines(lines)
                if summarized != chosen_lines:
                    chosen_lines = summarized
                    used_summary_fallback = True
            if chosen_lines and not self._fits(parts, title, chosen_lines):
                allowed = self._fit_lines(parts, title, chosen_lines)
                chosen_lines = allowed
                truncated = True
            section_map[title] = chosen_lines
            parts.append(f"[{title}]")
            parts.extend(chosen_lines)
            parts.append("")

        rendered = "\n".join(parts).strip() + "\n"
        token_count = self._token_count(rendered)
        if token_count > self.max_token_budget:
            truncated = True
            rendered = self._trim_rendered(rendered)
            token_count = self._token_count(rendered)
        return rendered, token_count, truncated, used_summary_fallback, section_map

    def _fits(self, existing_parts: list[str], title: str, lines: list[str]) -> bool:
        candidate = "\n".join([*existing_parts, f"[{title}]", *lines, ""])
        return self._token_count(candidate) <= self.max_token_budget

    def _fit_lines(self, existing_parts: list[str], title: str, lines: list[str]) -> list[str]:
        kept: list[str] = []
        for line in lines:
            candidate = [*kept, line]
            if not self._fits(existing_parts, title, candidate):
                break
            kept.append(line)
        return kept

    def _summarize_lines(self, lines: list[str], *, policy: ContextBudgetPolicy | None = None) -> list[str]:
        if not lines:
            return []
        line_limit = policy.summarize_line_limit if policy else 3
        token_limit = policy.summarize_token_limit_per_line if policy else 8
        summaries: list[str] = []
        for line in lines[:line_limit]:
            tokens = line.split()
            summaries.append(" ".join(tokens[:token_limit]))
        return [f"- Summary: {' | '.join(summaries)}"]

    def _trim_rendered(self, rendered: str) -> str:
        tokens = rendered.split()
        return " ".join(tokens[: self.max_token_budget])

    def _token_count(self, text: str) -> int:
        return len(text.split())

    def _auto_page(self, results: list) -> list:
        if not results:
            return results
        total = sum(self._estimate_tokens(r.content) for r in results)
        if total <= self.max_token_budget:
            return results
        paged = sorted(results, key=lambda r: r.final_score, reverse=True)
        budget_left = self.max_token_budget
        kept: list = []
        for r in paged:
            cost = self._estimate_tokens(r.content)
            if cost <= budget_left:
                kept.append(r)
                budget_left -= cost
            else:
                break
        return kept if kept else paged[:3]

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        return max(1, len(text.split()))
