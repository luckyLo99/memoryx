import json
import subprocess
import sys

from memoryx.diagnostics.replay_exporter import (
    ReplayExporter,
    export_replay_from_events,
    export_replay_jsonl_to_file,
)
from memoryx.diagnostics.schemas import ReplayCase, ReplayStep


def test_replay_case_round_trip_to_dict_json_from_dict():
    case = ReplayCase(
        replay_id="replay-1",
        source_trace_ids=["trace-1"],
        session_id_hash="hash-1",
        memoryx_version="2.0.0",
        hermes_version="h1",
        scenario="scenario",
        steps=[ReplayStep(step_id="1", phase="on_user_message", input_preview="hello")],
        expected_behavior="expected",
        observed_behavior="observed",
        redacted_inputs=["hello"],
        memory_refs=["m1"],
        guard_decisions=["allow"],
        failure_signature="sig",
    )
    payload = case.to_dict()
    restored = ReplayCase.from_dict(json.loads(case.to_json()))
    assert payload["privacy_level"] == "redacted"
    assert restored.to_dict() == payload


def test_export_replay_from_events_sets_redacted_privacy_level():
    case = export_replay_from_events(
        [{"trace_id": "t1", "session_id": "s1", "phase": "on_user_message", "decision": "allow"}],
        scenario="s",
        expected_behavior="e",
        observed_behavior="o",
    )
    assert case.privacy_level == "redacted"


def test_replay_does_not_contain_api_key_or_memoryx_home():
    key_name = "OPENAI" + "_API_KEY"
    case = export_replay_from_events(
        [
            {
                "trace_id": "t1",
                "session_id": "s1",
                "phase": "on_tool_call",
                "redacted_input_preview": f"{key_name}=fake-test-value /home/lucky/.memoryx/data/memoryx.db",
                "metadata": {"api_key": "abc123"},
            }
        ],
        scenario="s",
        expected_behavior="e",
        observed_behavior="o",
    )
    dumped = case.to_json()
    assert "fake-test-value" not in dumped
    assert "abc123" not in dumped
    assert "/home/lucky/.memoryx" not in dumped


def test_malformed_jsonl_is_skipped_and_warning_recorded(tmp_path):
    trace = tmp_path / "trace.jsonl"
    trace.write_text('{"trace_id":"t1","session_id":"s1","phase":"p"}\nnot-json\n', encoding="utf-8")
    exporter = ReplayExporter()
    events = exporter.load_trace_jsonl(trace)
    assert len(events) == 1
    assert exporter.warnings


def test_cli_exports_replay_json_from_trace_jsonl(tmp_path):
    trace = tmp_path / "trace.jsonl"
    replay = tmp_path / "out" / "replay.json"
    trace.write_text('{"trace_id":"t1","session_id":"s1","phase":"p","decision":"allow"}\n', encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "scripts/memoryx_export_replay.py",
            "--input",
            str(trace),
            "--output",
            str(replay),
            "--scenario",
            "scenario",
            "--expected",
            "expected",
            "--observed",
            "observed",
        ],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert "replay_export: PASS" in result.stdout
    payload = json.loads(replay.read_text(encoding="utf-8"))
    assert payload["privacy_level"] == "redacted"


def test_memory_refs_are_deduplicated():
    case = export_replay_from_events(
        [
            {"trace_id": "t1", "session_id": "s1", "phase": "p", "memory_ids": ["m1", "m1"], "evidence_ids": ["m1", "e2"]}
        ],
        scenario="s",
        expected_behavior="e",
        observed_behavior="o",
    )
    assert case.memory_refs == ["m1", "e2"]


def test_session_id_is_hashed_not_output_raw():
    case = export_replay_from_events(
        [{"trace_id": "t1", "session_id": "session-secret", "phase": "p"}],
        scenario="s",
        expected_behavior="e",
        observed_behavior="o",
    )
    dumped = case.to_json()
    assert "session-secret" not in dumped
    assert case.session_id_hash


def test_export_replay_jsonl_to_file_writes_redacted_payload(tmp_path):
    trace = tmp_path / "trace.jsonl"
    output = tmp_path / "replay.json"
    trace.write_text('{"trace_id":"t1","session_id":"s1","phase":"p","redacted_input_preview":"token=abc"}\n', encoding="utf-8")
    case = export_replay_jsonl_to_file(trace, output, "s", "e", "o")
    dumped = output.read_text(encoding="utf-8")
    assert case.privacy_level == "redacted"
    assert "abc" not in dumped
