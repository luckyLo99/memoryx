from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

ALLOWED_DECISIONS = {
    "memoryx_bug",
    "hermes_integration_bug",
    "model_behavior",
    "configuration_error",
    "data_quality_issue",
    "unknown",
}
ALLOWED_SEVERITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_RELEASE_IMPACTS = {"none", "v2.0.1", "v3.0.0-rc.1"}
REQUIRED_FIELDS = [
    "phase",
    "decision",
    "severity",
    "confidence",
    "summary",
    "evidence",
    "root_cause",
    "reproduction_steps",
    "allowed_files",
    "forbidden_files",
    "recommended_tests",
    "patch_plan",
    "release_impact",
    "requires_user_confirmation",
    "stop_reason",
]

SYSTEM_PROMPT = """你是 MemoryX 生产诊断 agent。
你只能做诊断、归因、复现建议、测试建议和 patch plan。
你不执行 shell。
你不执行 patch。
你不 commit。
你不 tag。
你不 release。
你不修改 stable runtime。
你不建议用 skip/xfail 清失败。
你不建议关闭 SQLite foreign_keys。
你不建议使用 INSERT OR IGNORE 掩盖 FK 或 parent row 问题。
你必须只输出 JSON。
证据不足时 decision=unknown，不得猜测。
"""


class DiagnosisClient(Protocol):
    def diagnose(
        self,
        *,
        model: str,
        system_prompt: str,
        replay: dict[str, Any],
        max_output_tokens: int,
        temperature: float,
        reasoning_effort: str,
    ) -> str:
        ...


@dataclass
class DiagnosisResult:
    phase: str
    decision: str
    severity: str
    confidence: float
    summary: str
    evidence: list[dict[str, Any]] = field(default_factory=list)
    root_cause: str = ""
    reproduction_steps: list[str] = field(default_factory=list)
    allowed_files: list[str] = field(default_factory=list)
    forbidden_files: list[str] = field(default_factory=list)
    recommended_tests: list[str] = field(default_factory=list)
    patch_plan: list[str] = field(default_factory=list)
    release_impact: str = "none"
    requires_user_confirmation: bool = True
    stop_reason: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DiagnosisResult":
        data = validate_diagnosis_payload(payload)
        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "decision": self.decision,
            "severity": self.severity,
            "confidence": self.confidence,
            "summary": self.summary,
            "evidence": self.evidence,
            "root_cause": self.root_cause,
            "reproduction_steps": self.reproduction_steps,
            "allowed_files": self.allowed_files,
            "forbidden_files": self.forbidden_files,
            "recommended_tests": self.recommended_tests,
            "patch_plan": self.patch_plan,
            "release_impact": self.release_impact,
            "requires_user_confirmation": self.requires_user_confirmation,
            "stop_reason": self.stop_reason,
        }


def parse_diagnosis_json(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid diagnosis JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError("diagnosis JSON must be an object")
    return payload


def _list_of_str(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return [str(item) for item in value]


def validate_diagnosis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        raise ValueError("diagnosis payload missing fields: " + ", ".join(missing))

    decision = str(payload["decision"])
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"invalid decision: {decision}")
    severity = str(payload["severity"])
    if severity not in ALLOWED_SEVERITIES:
        raise ValueError(f"invalid severity: {severity}")
    release_impact = str(payload["release_impact"])
    if release_impact not in ALLOWED_RELEASE_IMPACTS:
        raise ValueError(f"invalid release_impact: {release_impact}")

    evidence = payload["evidence"]
    if not isinstance(evidence, list):
        raise ValueError("evidence must be a list")
    normalized_evidence = []
    for item in evidence:
        if not isinstance(item, dict):
            raise ValueError("evidence items must be objects")
        normalized_evidence.append(dict(item))

    try:
        confidence = float(payload["confidence"])
    except (TypeError, ValueError) as exc:
        raise ValueError("confidence must be numeric") from exc
    if confidence < 0.0 or confidence > 1.0:
        raise ValueError("confidence must be between 0.0 and 1.0")

    return {
        "phase": str(payload["phase"]),
        "decision": decision,
        "severity": severity,
        "confidence": confidence,
        "summary": str(payload["summary"]),
        "evidence": normalized_evidence,
        "root_cause": str(payload["root_cause"]),
        "reproduction_steps": _list_of_str(payload["reproduction_steps"], "reproduction_steps"),
        "allowed_files": _list_of_str(payload["allowed_files"], "allowed_files"),
        "forbidden_files": _list_of_str(payload["forbidden_files"], "forbidden_files"),
        "recommended_tests": _list_of_str(payload["recommended_tests"], "recommended_tests"),
        "patch_plan": _list_of_str(payload["patch_plan"], "patch_plan"),
        "release_impact": release_impact,
        "requires_user_confirmation": bool(payload["requires_user_confirmation"]),
        "stop_reason": str(payload["stop_reason"]),
    }


class GPTDiagnoser:
    def __init__(self, *, client: DiagnosisClient, model: str = "gpt-5.5") -> None:
        if model != "gpt-5.5":
            raise ValueError("GPTDiagnoser only allows model='gpt-5.5'")
        self.client = client
        self.model = model

    def diagnose(
        self,
        replay: dict[str, Any],
        *,
        max_output_tokens: int = 1000,
        temperature: float = 0.0,
        reasoning_effort: str = "medium",
    ) -> DiagnosisResult:
        if not isinstance(replay, dict):
            raise ValueError("replay must be a dict")
        if replay.get("privacy_level") != "redacted":
            raise ValueError("replay privacy_level must be redacted")

        last_error: Exception | None = None
        for _ in range(2):
            text = self.client.diagnose(
                model=self.model,
                system_prompt=SYSTEM_PROMPT,
                replay=replay,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                reasoning_effort=reasoning_effort,
            )
            try:
                return DiagnosisResult.from_dict(parse_diagnosis_json(text))
            except ValueError as exc:
                last_error = exc
        raise ValueError(f"diagnosis failed after retry: {last_error}")
