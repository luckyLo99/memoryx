from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ReplayStep:
    step_id: str
    phase: str
    input_preview: str = ""
    decision: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReplayStep":
        return cls(
            step_id=str(data.get("step_id", "")),
            phase=str(data.get("phase", "")),
            input_preview=str(data.get("input_preview", "")),
            decision=str(data.get("decision", "unknown")),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class TraceEvent:
    trace_id: str = ""
    session_id: str = ""
    phase: str = ""
    timestamp: str = ""
    memoryx_version: str = "2.0.0"
    hermes_version: str = ""
    code_commit: str = ""
    input_hash: str = ""
    redacted_input_preview: str = ""
    memory_ids: list[str] = field(default_factory=list)
    decision: str = "unknown"
    degraded: bool = False
    warnings: list[str] = field(default_factory=list)
    latency_ms: int = 0
    error_type: str = ""
    error_message_redacted: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TraceEvent":
        return cls(
            trace_id=str(data.get("trace_id", "")),
            session_id=str(data.get("session_id", "")),
            phase=str(data.get("phase", "")),
            timestamp=str(data.get("timestamp", "")),
            memoryx_version=str(data.get("memoryx_version", "2.0.0")),
            hermes_version=str(data.get("hermes_version", "")),
            code_commit=str(data.get("code_commit", "")),
            input_hash=str(data.get("input_hash", "")),
            redacted_input_preview=str(data.get("redacted_input_preview", data.get("input_preview", ""))),
            memory_ids=list(data.get("memory_ids") or []),
            decision=str(data.get("decision", "unknown")),
            degraded=bool(data.get("degraded", False)),
            warnings=list(data.get("warnings") or []),
            latency_ms=int(data.get("latency_ms", 0) or 0),
            error_type=str(data.get("error_type", "")),
            error_message_redacted=str(data.get("error_message_redacted", data.get("error_message", ""))),
            evidence_ids=list(data.get("evidence_ids") or []),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class ReplayCase:
    replay_id: str
    source_trace_ids: list[str]
    session_id_hash: str
    memoryx_version: str
    hermes_version: str
    scenario: str
    steps: list[ReplayStep]
    expected_behavior: str
    observed_behavior: str
    redacted_inputs: list[str]
    memory_refs: list[str]
    guard_decisions: list[str]
    failure_signature: str
    privacy_level: str = "redacted"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["steps"] = [step.to_dict() if isinstance(step, ReplayStep) else step for step in self.steps]
        payload["privacy_level"] = "redacted"
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReplayCase":
        return cls(
            replay_id=str(data.get("replay_id", "")),
            source_trace_ids=list(data.get("source_trace_ids") or []),
            session_id_hash=str(data.get("session_id_hash", "")),
            memoryx_version=str(data.get("memoryx_version", "2.0.0")),
            hermes_version=str(data.get("hermes_version", "")),
            scenario=str(data.get("scenario", "")),
            steps=[ReplayStep.from_dict(step) if isinstance(step, dict) else step for step in (data.get("steps") or [])],
            expected_behavior=str(data.get("expected_behavior", "")),
            observed_behavior=str(data.get("observed_behavior", "")),
            redacted_inputs=list(data.get("redacted_inputs") or []),
            memory_refs=list(data.get("memory_refs") or []),
            guard_decisions=list(data.get("guard_decisions") or []),
            failure_signature=str(data.get("failure_signature", "")),
            privacy_level="redacted",
            created_at=str(data.get("created_at", "")),
        )
