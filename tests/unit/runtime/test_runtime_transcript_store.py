from memoryx.runtime_context import RuntimeContextBudget, RuntimeTranscriptStore

def test_transcript_store_records_summarized_output(tmp_path):
    db = str(tmp_path / "m.db")
    budget = RuntimeContextBudget(max_command_stdout_chars=1000, max_terminal_lines=20)
    store = RuntimeTranscriptStore(db, budget)
    event = store.record_command(event_id="e1", task_id="t1", request_id="r1", command="cmd", exit_code=0, duration_ms=1, stdout="\n".join("x" * 100 for _ in range(1000)), stderr="")
    assert event.stdout_truncated
    events = store.recent_events("t1")
    assert len(events) == 1
    assert events[0].event_id == "e1"
