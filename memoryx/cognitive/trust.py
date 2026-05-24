from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


SOURCE_BASE_TRUST = {
    "user_explicit": 0.95,
    "tool_verified": 0.90,
    "system_event": 0.85,
    "conversation_log": 0.75,
    "agent_inferred": 0.45,
    "agent_reflection": 0.35,
    "unknown": 0.40,
}


@dataclass(slots=True)
class TrustDecision:
    trust_score: float
    should_inject: bool
    reason: str


class MemoryTrustScorer:
    """Score a memory's trustworthiness based on source, verification, and decay.

    Core rule: agent_reflection / agent_inferred without verification
    should NOT be injected as high-confidence facts into LLM context.
    """

    def score(self, memory: dict[str, Any]) -> TrustDecision:
        source_type = str(memory.get("source_type") or "unknown")
        verification = str(memory.get("verification_status") or "unverified")
        confidence = float(memory.get("confidence_score") or memory.get("confidence") or 0.5)
        importance = float(memory.get("importance_score") or memory.get("importance") or 0.5)

        base = SOURCE_BASE_TRUST.get(source_type, 0.40)

        if verification == "verified":
            base += 0.15
        elif verification == "contradicted":
            base -= 0.45
        elif verification == "user_rejected":
            base -= 0.60

        expires_at = memory.get("expires_at")
        if expires_at:
            try:
                exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                if exp < datetime.now(timezone.utc):
                    base -= 0.40
            except Exception:
                pass

        trust = max(0.0, min(1.0, base * 0.6 + confidence * 0.25 + importance * 0.15))

        should_inject = trust >= 0.55

        # Core rule: agent's own reflections cannot enter context as facts
        # unless explicitly verified
        if source_type == "agent_reflection" and verification != "verified":
            should_inject = False

        return TrustDecision(
            trust_score=round(trust, 2),
            should_inject=should_inject,
            reason=f"source={source_type}, verification={verification}, trust={trust:.2f}",
        )