import json

import pytest

from memoryx.diagnostics.gpt_diagnoser import (
    GPTDiagnoser,
    parse_diagnosis_json,
    validate_diagnosis_payload,
)


VALID_PAYLOAD = {
    "phase": "diagnosis",
    "decision": "memoryx_bug",
    "severity": "P1",
    "confidence": 0.8,
    "summary": "summary",
    "evidence": [{"source": "replay", "id": "r1", "detail": "detail"}],
    "root_cause": "cause",
    "reproduction_steps": ["step"],
    "allowed_files": ["memoryx/diagnostics/gpt_diagnoser.py"],
    "forbidden_files": ["/home/lucky/runtime/memoryx-2.0.0"],
    "recommended_tests": ["tests/test_gpt_diagnoser_contract.py"],
    "patch_plan": ["plan"],
    "release_impact": "none",
    "requires_user_confirmation": True,
    "stop_reason": "",
}


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def diagnose(self, *, model, system_prompt, replay, max_output_tokens, temperature, reasoning_effort):
        self.calls.append(
            {
                "model": model,
                "system_prompt": system_prompt,
                "replay": replay,
                "max_output_tokens": max_output_tokens,
                "temperature": temperature,
                "reasoning_effort": reasoning_effort,
            }
        )
        return self.responses.pop(0)


def redacted_replay():
    return {
        "replay_id": "r1",
        "privacy_level": "redacted",
        "scenario": "s",
        "steps": [],
        "redacted_inputs": [],
    }


def test_default_model_is_gpt_5_5_only():
    diagnoser = GPTDiagnoser(client=FakeClient([json.dumps(VALID_PAYLOAD)]))
    assert diagnoser.model == "gpt-5.5"


def test_other_model_raises_value_error():
    with pytest.raises(ValueError):
        GPTDiagnoser(client=FakeClient([]), model="gpt-5.5-pro")


def test_non_redacted_replay_is_rejected():
    diagnoser = GPTDiagnoser(client=FakeClient([]))
    replay = redacted_replay()
    replay["privacy_level"] = "private"
    with pytest.raises(ValueError):
        diagnoser.diagnose(replay)


def test_valid_json_is_parsed():
    parsed = parse_diagnosis_json(json.dumps(VALID_PAYLOAD))
    assert parsed["decision"] == "memoryx_bug"


def test_invalid_json_triggers_one_retry():
    client = FakeClient(["not-json", json.dumps(VALID_PAYLOAD)])
    result = GPTDiagnoser(client=client).diagnose(redacted_replay())
    assert result.decision == "memoryx_bug"
    assert len(client.calls) == 2


def test_retry_after_invalid_json_still_invalid_raises():
    client = FakeClient(["not-json", "still-not-json"])
    with pytest.raises(ValueError):
        GPTDiagnoser(client=client).diagnose(redacted_replay())
    assert len(client.calls) == 2


def test_missing_schema_field_raises():
    payload = dict(VALID_PAYLOAD)
    payload.pop("summary")
    with pytest.raises(ValueError):
        validate_diagnosis_payload(payload)


def test_invalid_decision_raises():
    payload = dict(VALID_PAYLOAD)
    payload["decision"] = "other"
    with pytest.raises(ValueError):
        validate_diagnosis_payload(payload)


def test_invalid_severity_raises():
    payload = dict(VALID_PAYLOAD)
    payload["severity"] = "P9"
    with pytest.raises(ValueError):
        validate_diagnosis_payload(payload)


def test_invalid_release_impact_raises():
    payload = dict(VALID_PAYLOAD)
    payload["release_impact"] = "v3"
    with pytest.raises(ValueError):
        validate_diagnosis_payload(payload)


def test_fake_client_only_receives_diagnostic_prompt_not_execution_tools():
    client = FakeClient([json.dumps(VALID_PAYLOAD)])
    GPTDiagnoser(client=client).diagnose(redacted_replay())
    call = client.calls[0]
    prompt = call["system_prompt"]
    assert call["model"] == "gpt-5.5"
    assert "不执行 shell" in prompt
    assert "不执行 patch" in prompt
    assert "不 commit" in prompt
    assert "不 tag" in prompt
    assert "不 release" in prompt
    assert "skip/xfail" in prompt
    assert "SQLite foreign_keys" in prompt
    assert "INSERT OR IGNORE" in prompt
