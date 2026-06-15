from __future__ import annotations

import html
import json
import re
from memoryx.retrieval import RetrievalResult
from memoryx.routing import RoutePlan
from memoryx.safety.llm_firewall import LLMFirewall, safety_preamble

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
    """Backward-compatible helper that now returns isolated memory data."""
    metadata = {}
    if evidence:
        metadata["evidence"] = getattr(result, "evidence_level", None) or "unknown"
    if source:
        metadata["source"] = getattr(result, "source_type", None) or "unknown"
    if layer:
        metadata["layer"] = _resolve_layer_from_result(result) or "legacy"
    annotation = " ".join(f"{key}={value}" for key, value in metadata.items())
    content = str(getattr(result, "content", ""))
    if annotation:
        content = f"{annotation}\n{content}"
    return LLMFirewall().wrap_untrusted_memory(
        content,
        memory_id=str(getattr(result, "memory_id", "")),
    )


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


class ContextAssemblyEngine:
    def __init__(self, max_token_budget: int = 1200, policy: ContextBudgetPolicy | None = None) -> None:
        self.max_token_budget = max_token_budget
        self.policy = policy or ContextBudgetPolicy.from_max_token_budget(max_token_budget)
        self.firewall = LLMFirewall()

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

        wc = [
            self._wrap_untrusted_text(
                line,
                record_id=f"working_context:{idx}",
                source="memoryx.working_context",
                kind="session_context",
            )
            for idx, line in enumerate(working_context or [])
        ]
        oc = [
            self._wrap_untrusted_text(
                line,
                record_id=f"open_conflict:{idx}",
                source="memoryx.conflict",
                kind="session_context",
            )
            for idx, line in enumerate(open_conflicts or [])
        ]
        warnings_lines = list(oc)

        # Build ordered sections with quota info
        section_specs: list[dict] = [
            {"title": "MemoryX Safety Contract", "lines": [safety_preamble()], "quota": 9999, "hard": True, "key": "safety_contract"},
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
            {"title": "Recent Conversation", "lines": [
                self._wrap_untrusted_text(
                    line,
                    record_id=f"recent:{idx}",
                    source="memoryx.recent_conversation",
                    kind="session_context",
                )
                for idx, line in enumerate(recent_conversation)
            ], "quota": 9999, "hard": False, "key": "recent"},
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
            rendered = self._trim_parts_to_budget(parts, max_tokens)
            token_count = self._token_count(rendered)
            if "<untrusted_" in rendered and not self._untrusted_blocks_are_balanced(rendered):
                rendered = safety_preamble()
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

    def _trim_parts_to_budget(self, parts: list[str], max_tokens: int) -> str:
        kept = list(parts)
        while kept:
            rendered = "\n".join(kept).strip() + "\n"
            if self._token_count(rendered) <= max_tokens and self._untrusted_blocks_are_balanced(rendered):
                return rendered

            remove_idx = None
            for idx in range(len(kept) - 1, -1, -1):
                part = kept[idx].strip()
                if not part or (part.startswith("[") and part.endswith("]")):
                    continue
                remove_idx = idx
                break
            if remove_idx is None:
                kept.pop()
            else:
                kept.pop(remove_idx)

        return safety_preamble()

    @staticmethod
    def _untrusted_blocks_are_balanced(text: str) -> bool:
        tags = ("memory", "session_context", "tool_output", "artifact", "context")
        for tag in tags:
            opening = text.count(f"<untrusted_{tag}>")
            closing = text.count(f"</untrusted_{tag}>")
            if opening != closing:
                return False
        return True

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
            line = self._wrap_result(result, progressive=progressive)

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

    def _wrap_result(self, result: RetrievalResult, *, progressive: bool = False) -> str:
        layer = _resolve_layer_from_result(result) or "legacy"
        metadata = {
            "memory_type": result.memory_type,
            "scope": result.scope,
            "layer": layer,
            "score": round(float(result.final_score), 4),
            "source_type": getattr(result, "source_type", "unknown"),
            "verification_status": getattr(result, "verification_status", "unverified"),
            "trust_score": round(float(getattr(result, "trust_score", 0.5)), 4),
        }
        if progressive:
            content = (
                f"memory_id={result.memory_id}; memory_type={result.memory_type}; "
                f"scope={result.scope}; layer={layer}; score={result.final_score:.2f}"
            )
        else:
            content = result.content
        return self._wrap_untrusted_text(
            content,
            record_id=result.memory_id,
            source="memoryx.retrieval",
            kind="memory",
            metadata=metadata,
        )

    def _wrap_untrusted_text(
        self,
        text: str,
        *,
        record_id: str | None,
        source: str,
        kind: str,
        metadata: dict | None = None,
    ) -> str:
        if kind == "memory":
            decision = self.firewall.inspect_memory_context_sync(text)
            return self.firewall.wrap_untrusted_memory(
                text,
                memory_id=record_id,
                risk_flags=decision.flags,
            )
        from memoryx.safety.context_isolation import wrap_untrusted_session_context

        decision = self.firewall.inspect_memory_context_sync(text)
        return wrap_untrusted_session_context(
            text,
            record_id=record_id,
            source=source,
            risk_flags=decision.flags,
            metadata=metadata or {},
        )

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
            if "<untrusted_" in line:
                summaries.append(self._summarize_untrusted_line(line, token_limit=token_limit))
                continue
            tokens = line.split()
            summaries.append(" ".join(tokens[:token_limit]))
        if all("<untrusted_" in line for line in lines[:line_limit]):
            return summaries
        return [f"- Summary: {' | '.join(summaries)}"]

    def _summarize_untrusted_line(self, line: str, *, token_limit: int) -> str:
        content_match = re.search(r"<content>\s*(.*?)\s*</content>", line, flags=re.S)
        content = html.unescape(content_match.group(1).strip()) if content_match else ""
        preview = " ".join(content.split()[:token_limit]) or "[omitted untrusted context due to budget]"
        id_match = re.search(r'\bid="([^"]*)"', line)
        memory_id = html.unescape(id_match.group(1)) if id_match else None
        if "<untrusted_memory>" in line:
            return self.firewall.wrap_untrusted_memory(
                preview,
                memory_id=memory_id,
                risk_flags=["budget_summary"],
            )
        from memoryx.safety.context_isolation import wrap_untrusted_session_context

        return wrap_untrusted_session_context(
            preview,
            record_id=memory_id,
            source="memoryx.context_budget_summary",
            risk_flags=["budget_summary"],
        )

    def _trim_rendered(self, rendered: str) -> str:
        lines = rendered.splitlines()
        while lines and self._token_count("\n".join(lines) + "\n") > self.max_token_budget:
            remove_idx = None
            for idx in range(len(lines) - 1, -1, -1):
                line = lines[idx].strip()
                if not line or (line.startswith("[") and line.endswith("]")):
                    continue
                remove_idx = idx
                break
            if remove_idx is None:
                lines.pop()
            else:
                lines.pop(remove_idx)
        return "\n".join(lines).strip() + "\n"

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
