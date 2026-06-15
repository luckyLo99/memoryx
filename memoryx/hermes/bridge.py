"""Hermes-facing bridge for MemoryX.

This is the product integration layer that makes MemoryX affect agent behavior,
not merely log events. It returns structured blocks for Hermes to inject or use
for action gating.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from memoryx.conversation_log import ConversationLogStore
from memoryx.safety.llm_firewall import LLMFirewall, LLMSafetyDecision, safety_preamble

logger = logging.getLogger(__name__)

try:
    from memoryx.cognitive.guarded_generation import CognitiveGuard
except Exception:  # pragma: no cover
    CognitiveGuard = None  # type: ignore[assignment]

try:
    from memoryx.cognitive.narrative_reflection import NarrativeReflectionEngine
except Exception:  # pragma: no cover
    NarrativeReflectionEngine = None  # type: ignore[assignment]


@dataclass(slots=True)
class HermesBridgeResult:
    event: str
    session_id: str
    context_block: str = ""
    guard_block: str = ""
    decision: str = "allow"
    should_block: bool = False
    requires_user: bool = False
    memories: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class HermesMemoryBridge:
    def __init__(
        self,
        *,
        repository,
        query_api=None,
        retrieval_engine=None,
        lesson_policy=None,
        working_memory_engine=None,
        attention_focus_engine=None,
        golden_rule_engine=None,
        max_context_items: int = 6,
    ) -> None:
        self.repository = repository
        self.query_api = query_api
        self.retrieval_engine = retrieval_engine or getattr(query_api, "retrieval_engine", None)
        self.conversation_log = ConversationLogStore(repository)
        self.llm_firewall = LLMFirewall(repository=repository, strict=True)
        self.cognitive_guard = (
            CognitiveGuard(repository=repository, retrieval_engine=self.retrieval_engine, lesson_policy=lesson_policy)
            if CognitiveGuard is not None
            else None
        )
        self.narrative = NarrativeReflectionEngine(repository=repository) if NarrativeReflectionEngine is not None else None
        self.working_memory_engine = working_memory_engine
        self.attention_focus_engine = attention_focus_engine
        self.golden_rule_engine = golden_rule_engine
        self.max_context_items = max_context_items

    async def on_user_message(self, *, session_id: str, content: str, **extra: Any) -> HermesBridgeResult:
        try:
            safety = await self.llm_firewall.inspect_user_input(content, session_id=session_id)
        except Exception:
            logger.warning("Firewall inspect_user_input failed, using conservative block decision", exc_info=True)
            safety = LLMSafetyDecision(
                decision_id="firewall_error",
                surface="user_input",
                decision="block",
                severity="high",
                reason="Firewall error: content blocked as precaution",
                flags=["firewall_error"],
            )

        try:
            await self.conversation_log.log_turn(session_id=session_id, role="user", content=content)
        except Exception:
            logger.warning("conversation_log.log_turn failed for user message", exc_info=True)

        # ── Attention Focus: track interruptions and mainline ──
        attention_result: dict[str, Any] = {}
        if self.attention_focus_engine is not None:
            try:
                attention_result = await self.attention_focus_engine.on_user_message(session_id, content)
            except Exception:
                logger.warning("attention_focus_engine.on_user_message failed", exc_info=True)

        # ── Golden Rules: detect user corrections ──
        golden_rule_applied = False
        if self.golden_rule_engine is not None:
            try:
                if self.golden_rule_engine.detect_correction(content):
                    # User is correcting us — extract and create golden rule
                    corrected_fact = self.golden_rule_engine.extract_corrected_fact(content)
                    if corrected_fact:
                        # Store as a golden memory
                        from memoryx.storage.repository import MemoryRecord
                        record = MemoryRecord(
                            content=corrected_fact,
                            memory_type="FACT",
                            scope="user",
                            importance_score=1.0,
                            confidence_score=1.0,
                            tags=["golden_rule", "user_correction"],
                        )
                        mem_id = await self.repository.store_memory(record)
                        await self.golden_rule_engine.create_golden_rule(
                            memory_id=mem_id,
                            corrected_content=corrected_fact,
                            original_content=extra.get("last_assistant_message", ""),
                            scope="global",
                            session_id=session_id,
                        )
                        golden_rule_applied = True
            except Exception:
                logger.warning("golden_rule_engine processing failed", exc_info=True)

        memories: list[dict[str, Any]] = []
        if self.query_api is not None and hasattr(self.query_api, "search"):
            try:
                memories = await self.query_api.search(
                    query=content,
                    query_vector=[],
                    limit=self.max_context_items,
                    session_id=session_id,
                    include_global=True,
                    include_lessons=True,
                    explain_scores=True,
                )
            except Exception:
                logger.warning("query_api.search failed", exc_info=True)
                memories = []

        # ── Apply Golden Rules to retrieved memories ──
        if self.golden_rule_engine is not None and memories:
            try:
                memories = await self.golden_rule_engine.apply_golden_rules(memories, content, session_id)
            except Exception:
                logger.warning("golden_rule_engine.apply_golden_rules failed", exc_info=True)

        context_block = self.render_context_block(memories=memories, safety_block=self.llm_firewall.render_policy_block(safety))

        # Inject attention focus context (主线恢复提示)
        if attention_result.get("action") == "returned" and attention_result.get("restored_context"):
            restored = attention_result["restored_context"]
            restore_block = (
                "<attention_restore>\n"
                f"Restored focus: {restored['task_description']}\n"
                f"Reasoning: {' -> '.join(restored.get('reasoning_chain', [])[-3:])}\n"
                "</attention_restore>"
            )
            context_block = restore_block + "\n\n" + context_block

        # Inject working memory context (L0), if available
        working_lines: list[str] = []
        if self.working_memory_engine is not None:
            try:
                snap = await self.working_memory_engine.snapshot(session_id)
                if snap and snap.get("has_state"):
                    working_lines = snap["lines"]
            except Exception:
                logger.warning("working_memory_engine.snapshot failed", exc_info=True)
        if working_lines:
            working_block = "<working_context>\n" + "\n".join(working_lines) + "\n</working_context>"
            context_block = working_block + "\n\n" + context_block

        # Inject open conflict warning (24.3D-D)
        conflict_warning: str | None = None
        if hasattr(self.repository, "count_open_conflicts"):
            try:
                oc = await self.repository.count_open_conflicts()
                if oc > 0:
                    conflict_warning = (
                        "<conflict_warning>\n"
                        f"- {oc} open memory conflict(s) require review.\n"
                        "</conflict_warning>"
                    )
            except Exception:
                logger.warning("count_open_conflicts failed", exc_info=True)
        if conflict_warning:
            context_block = conflict_warning + "\n\n" + context_block

        metadata: dict[str, Any] = {"flags": safety.flags}
        if attention_result:
            metadata["attention"] = attention_result.get("action")
        if golden_rule_applied:
            metadata["golden_rule_created"] = True

        return HermesBridgeResult(
            event="on_user_message",
            session_id=session_id,
            context_block=context_block,
            guard_block=self.llm_firewall.render_policy_block(safety),
            decision=safety.decision,
            should_block=safety.should_block,
            requires_user=safety.requires_user,
            memories=memories,
            metadata=metadata,
        )

    async def on_tool_call(
        self,
        *,
        session_id: str,
        tool_name: str,
        args: dict[str, Any] | None = None,
        intent: str | None = None,
        **extra: Any,
    ) -> HermesBridgeResult:
        try:
            firewall_decision = await self.llm_firewall.evaluate_tool_call(
                tool_name=tool_name,
                args=args or {},
                session_id=session_id,
            )
        except Exception:
            logger.warning("Firewall evaluate_tool_call failed, using conservative block decision", exc_info=True)
            firewall_decision = LLMSafetyDecision(
                decision_id="firewall_error",
                surface="tool_call",
                decision="block",
                severity="high",
                reason="Firewall error: tool call blocked as precaution",
                flags=["firewall_error"],
            )
        guard_block = self.llm_firewall.render_policy_block(firewall_decision)
        decision = firewall_decision.decision
        should_block = firewall_decision.should_block
        requires_user = firewall_decision.requires_user

        if self.cognitive_guard is not None:
            try:
                action_text = f"{tool_name} {args or {}}"
                action_guard = await self.cognitive_guard.evaluate_action(
                    action_text=action_text,
                    intent=intent,
                    session_id=session_id,
                    store=True,
                )
                if action_guard.guard_block:
                    guard_block = (guard_block + "\n\n" + action_guard.guard_block).strip()
                priority = {
                    "allow": 0,
                    "warn": 1,
                    "require_confirmation": 2,
                    "require_tool_verification": 3,
                    "require_dry_run": 4,
                    "block": 5,
                }
                if priority.get(action_guard.enforcement.decision, 0) > priority.get(decision, 0):
                    decision = action_guard.enforcement.decision
                should_block = should_block or action_guard.should_block
                requires_user = requires_user or action_guard.requires_user
            except Exception:
                logger.warning("cognitive_guard.evaluate_action failed", exc_info=True)

        return HermesBridgeResult(
            event="on_tool_call",
            session_id=session_id,
            guard_block=guard_block,
            decision=decision,
            should_block=should_block,
            requires_user=requires_user,
            metadata={"tool_name": tool_name},
        )

    async def on_tool_result(
        self,
        *,
        session_id: str,
        tool_name: str,
        result: Any,
        **extra: Any,
    ) -> HermesBridgeResult:
        text = result if isinstance(result, str) else str(result)
        try:
            safety = await self.llm_firewall.inspect_tool_output(text, session_id=session_id)
        except Exception:
            logger.warning("Firewall inspect_tool_output failed, using conservative block decision", exc_info=True)
            safety = LLMSafetyDecision(
                decision_id="firewall_error",
                surface="tool_output",
                decision="block",
                severity="high",
                reason="Firewall error: tool output blocked as precaution",
                flags=["firewall_error"],
            )
        return HermesBridgeResult(
            event="on_tool_result",
            session_id=session_id,
            context_block=safety.sanitized_text or "",
            guard_block=self.llm_firewall.render_policy_block(safety),
            decision=safety.decision,
            should_block=safety.should_block,
            requires_user=safety.requires_user,
            metadata={"tool_name": tool_name},
        )

    async def on_assistant_response(self, *, session_id: str, content: str, question: str = "", **extra: Any) -> HermesBridgeResult:
        try:
            await self.conversation_log.log_turn(session_id=session_id, role="assistant", content=content)
        except Exception:
            logger.warning("conversation_log.log_turn failed for assistant message", exc_info=True)

        try:
            safety = await self.llm_firewall.inspect_assistant_output(content, session_id=session_id)
        except Exception:
            logger.warning("Firewall inspect_assistant_output failed, using conservative block decision", exc_info=True)
            safety = LLMSafetyDecision(
                decision_id="firewall_error",
                surface="assistant_output",
                decision="block",
                severity="high",
                reason="Firewall error: assistant output blocked as precaution",
                flags=["firewall_error"],
            )

        guard_block = self.llm_firewall.render_policy_block(safety)
        decision = safety.decision
        should_block = safety.should_block

        if self.cognitive_guard is not None:
            try:
                checked = await self.cognitive_guard.verify_answer(
                    question=question,
                    answer=content,
                    session_id=session_id,
                    store=True,
                )
                if checked.guard_block:
                    guard_block = (guard_block + "\n\n" + checked.guard_block).strip()
                should_block = should_block or checked.should_block
                if checked.should_block:
                    decision = "block"
                elif checked.guard_block and decision == "allow":
                    decision = "warn"
            except Exception:
                logger.warning("cognitive_guard.verify_answer failed", exc_info=True)

        return HermesBridgeResult(
            event="on_assistant_response",
            session_id=session_id,
            guard_block=guard_block,
            decision=decision,
            should_block=should_block,
            requires_user=should_block,
            metadata={"flags": safety.flags},
        )

    async def on_session_end(self, *, session_id: str, **extra: Any) -> HermesBridgeResult:
        summary = ""
        if self.narrative is not None:
            try:
                end = datetime.now(timezone.utc)
                start = extra.get("window_start") or end.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                reflection = await self.narrative.generate(
                    window_start=start,
                    window_end=extra.get("window_end") or end.isoformat(),
                    session_id=session_id,
                    reflection_type="session",
                    store=True,
                )
                summary = reflection.summary
            except Exception:
                summary = ""
        return HermesBridgeResult(
            event="on_session_end",
            session_id=session_id,
            context_block=summary,
            metadata={"narrative_summary": bool(summary)},
        )

    def render_context_block(self, *, memories: list[dict[str, Any]], safety_block: str = "") -> str:
        lines = [safety_preamble()]
        if safety_block:
            lines.append(safety_block)
        if memories:
            lines.append("## MemoryX Relevant Context")
            for item in memories[: self.max_context_items]:
                memory_type = item.get("memory_type", "MEMORY")
                score = item.get("final_score", "")
                content = str(item.get("content", "")).strip().replace("\n", " ")
                ev = item.get("evidence_level") or "unknown"
                stype = item.get("source_type") or "unknown"
                lyr = item.get("memory_layer") or "unknown"
                lines.append(f"- [{memory_type} score={score} evidence={ev} source={stype} layer={lyr}] {content[:500]}")
        return "\n".join(lines).strip() + "\n"
