from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redactor import hash_text, redact_mapping, redact_text
from .schemas import ReplayCase, ReplayStep, TraceEvent


class ReplayExporter:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def load_trace_jsonl(self, path: str | Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        trace_path = Path(path)
        for line_no, line in enumerate(trace_path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                self.warnings.append(f"malformed line {line_no}: {exc.msg}")
                continue
            if not isinstance(parsed, dict):
                self.warnings.append(f"non-object line {line_no}")
                continue
            events.append(redact_mapping(parsed))
        return events

    def export_replay_from_events(
        self,
        events: list[dict[str, Any]],
        scenario: str,
        expected_behavior: str,
        observed_behavior: str,
    ) -> ReplayCase:
        redacted_events = [redact_mapping(event) for event in events]
        source_trace_ids: list[str] = []
        memory_refs: list[str] = []
        guard_decisions: list[str] = []
        redacted_inputs: list[str] = []
        steps: list[ReplayStep] = []
        failure_parts: list[str] = []
        session_id_hash = ""
        memoryx_version = "2.1.0"
        hermes_version = ""

        for index, event in enumerate(redacted_events, start=1):
            trace_id = str(event.get("trace_id", ""))
            if trace_id and trace_id not in source_trace_ids:
                source_trace_ids.append(trace_id)
            if not session_id_hash and event.get("session_id"):
                session_id_hash = hash_text(str(event.get("session_id")))
            memoryx_version = str(event.get("memoryx_version") or memoryx_version)
            hermes_version = str(event.get("hermes_version") or hermes_version)
            phase = redact_text(str(event.get("phase", "")))
            preview = redact_text(str(event.get("redacted_input_preview") or event.get("input_preview") or event.get("input") or ""))
            decision = redact_text(str(event.get("decision", "unknown")))
            if preview:
                redacted_inputs.append(preview)
            steps.append(
                ReplayStep(
                    step_id=str(index),
                    phase=phase,
                    input_preview=preview,
                    decision=decision,
                    metadata=redact_mapping(event.get("metadata") or {}),
                )
            )
            for key in ("memory_ids", "evidence_ids"):
                refs = event.get(key) or []
                if isinstance(refs, (str, int, float)):
                    refs = [refs]
                for ref in refs:
                    ref_text = redact_text(str(ref))
                    if ref_text and ref_text not in memory_refs:
                        memory_refs.append(ref_text)
            if decision and decision not in guard_decisions:
                guard_decisions.append(decision)
            guard_envelope = event.get("guard_envelope")
            if isinstance(guard_envelope, dict):
                envelope_decision = redact_text(str(guard_envelope.get("decision", "")))
                if envelope_decision and envelope_decision not in guard_decisions:
                    guard_decisions.append(envelope_decision)
            error_type = redact_text(str(event.get("error_type", "")))
            error_message = redact_text(str(event.get("error_message_redacted") or event.get("error_message") or ""))
            if phase or error_type or error_message:
                failure_parts.append(":".join(part for part in (phase, error_type, error_message) if part))

        replay_id = "replay-" + hash_text("|".join(source_trace_ids) or str(uuid.uuid4()))
        return ReplayCase(
            replay_id=replay_id,
            source_trace_ids=source_trace_ids,
            session_id_hash=session_id_hash,
            memoryx_version=memoryx_version,
            hermes_version=hermes_version,
            scenario=redact_text(scenario),
            steps=steps,
            expected_behavior=redact_text(expected_behavior),
            observed_behavior=redact_text(observed_behavior),
            redacted_inputs=redacted_inputs,
            memory_refs=memory_refs,
            guard_decisions=guard_decisions,
            failure_signature=redact_text("|".join(failure_parts)),
            privacy_level="redacted",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def export_replay_jsonl_to_file(
        self,
        input_path: str | Path,
        output_path: str | Path,
        scenario: str,
        expected_behavior: str,
        observed_behavior: str,
    ) -> ReplayCase:
        events = self.load_trace_jsonl(input_path)
        case = self.export_replay_from_events(events, scenario, expected_behavior, observed_behavior)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(case.to_json() + "\n", encoding="utf-8")
        return case


def load_trace_jsonl(path: str | Path) -> list[dict[str, Any]]:
    return ReplayExporter().load_trace_jsonl(path)


def export_replay_from_events(
    events: list[dict[str, Any]],
    scenario: str,
    expected_behavior: str,
    observed_behavior: str,
) -> ReplayCase:
    return ReplayExporter().export_replay_from_events(events, scenario, expected_behavior, observed_behavior)


def export_replay_jsonl_to_file(
    input_path: str | Path,
    output_path: str | Path,
    scenario: str,
    expected_behavior: str,
    observed_behavior: str,
) -> ReplayCase:
    return ReplayExporter().export_replay_jsonl_to_file(input_path, output_path, scenario, expected_behavior, observed_behavior)
