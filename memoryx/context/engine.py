from __future__ import annotations

import json
from memoryx.retrieval import RetrievalResult
from memoryx.routing import RoutePlan

from .models import ContextBundle


def _resolve_layer_from_result(result: RetrievalResult) -> str:
    """Extract memory_layer from a RetrievalResult's metadata_json if present."""
    raw = getattr(result, "metadata_json", "{}") or "{}"
    try:
        meta = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, ValueError):
        meta = {}
    return meta.get("memory_layer", "")


class ContextAssemblyEngine:
    def __init__(self, max_token_budget: int = 1200) -> None:
        self.max_token_budget = max_token_budget

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
    ) -> ContextBundle:
        deduped = self._deduplicate(route_plan.results)
        if progressive:
            deduped = self._auto_page(deduped)
        grouped = self._group_memories_by_layer(deduped, progressive=progressive)

        # Priority-ordered sections: policy -> project -> session -> long_term -> episodic
        sections: list[tuple[str, list[str]]] = [
            ("System Prompt", [system_prompt]),
            ("SOUL", [soul_prompt]),
            ("Current Task", [current_task]),
        ]

        # Policy/guard first (L4)
        if grouped["policy"]:
            sections.append(("Policy / Guard", grouped["policy"]))

        # Working context (L0) — if provided
        wc = working_context or []
        if wc:
            sections.append(("Working Context", wc))

        # Project (L2)
        if grouped["project"]:
            sections.append(("Project Context", grouped["project"]))

        # Session (L1)
        if grouped["session"]:
            sections.append(("Session Memory", grouped["session"]))

        # Long-term (L3): facts + preferences + lessons — always emit sections for backward compat
        sections.append(("Relevant Long-Term Memory", grouped["long_term"]))
        sections.append(("User Preferences", grouped["user"]))
        if grouped["lessons"]:
            sections.append(("Lessons", grouped["lessons"]))

        # Episodic — always emit for backward compat
        sections.append(("Relevant Episodes", grouped["episodic"]))

        sections.append(("Recent Conversation", recent_conversation))

        rendered, token_count, truncated, used_summary_fallback, section_map = self._render_with_budget(sections)

        # Build layer counts
        layer_counts: dict[str, int] = {}
        for layer_key in ("policy", "project", "session", "long_term", "user", "lessons", "episodic"):
            cnt = len(grouped.get(layer_key, []))
            if cnt > 0:
                layer_counts[layer_key] = cnt

        return ContextBundle(
            rendered=rendered,
            token_count=token_count,
            truncated=truncated,
            used_summary_fallback=used_summary_fallback,
            sections=section_map,
            # Legacy fields
            facts=grouped.get("long_term", []),
            preferences=grouped.get("user", []),
            lessons=grouped.get("lessons", []),
            project_state=grouped.get("project", []),
            warnings=[],
            degraded=False,
            total_candidates=0,
            token_budget=self.max_token_budget,
            # New layer fields
            working_context=wc,
            policy_context=grouped.get("policy", []),
            session_context=grouped.get("session", []),
            project_context=grouped.get("project", []),
            long_term_context=grouped.get("long_term", []) + grouped.get("user", []) + grouped.get("lessons", []),
            layer_counts=layer_counts,
        )

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

        Falls back to old scope/memory_type logic when memory_layer is missing.
        """
        grouped = {
            "policy": [],
            "project": [],
            "session": [],
            "long_term": [],
            "user": [],
            "lessons": [],
            "episodic": [],
        }
        for result in results:
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

    def _summarize_lines(self, lines: list[str]) -> list[str]:
        if not lines:
            return []
        summaries: list[str] = []
        for line in lines[:3]:
            tokens = line.split()
            summaries.append(" ".join(tokens[:8]))
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
