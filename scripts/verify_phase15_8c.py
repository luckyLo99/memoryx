from __future__ import annotations

import json
from pathlib import Path
import tempfile

from memoryx.runtime_context.hermes_policy import HermesContextPolicy, write_policy_files
from memoryx.runtime_context import RuntimeContextBudget, RuntimePromptAssembler, RuntimeTranscriptStore, TaskCapsule, TaskCapsuleStore

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        files = write_policy_files(str(root))

        policy_json = json.loads(Path(files["json"]).read_text(encoding="utf-8"))
        assert policy_json["disable_session_search"] is True
        assert policy_json["disable_auto_recall"] is True
        assert policy_json["disable_raw_terminal_injection"] is True
        assert policy_json["require_runtime_prompt_assembler"] is True
        assert policy_json["max_active_context_tokens"] == 64000

        text = Path(files["markdown"]).read_text(encoding="utf-8")
        assert "Do not call session_search" in text
        assert "RuntimePromptAssembler" in text
        assert "RuntimeCommandRunner" in text

        db = str(root / "firewall.db")
        budget = RuntimeContextBudget(max_prompt_tokens=64000, max_command_stdout_chars=8000)

        TaskCapsuleStore(db, budget).upsert(TaskCapsule(
            task_id="t",
            objective="Verify host context policy prevents old session recall.",
            constraints=["No session_search", "No auto recall", "No raw terminal injection"],
            completed_steps=[],
            current_state="Testing host policy capsule only.",
            next_steps=["Assemble bounded prompt"],
            updated_at="now",
        ))

        huge_old_recall = "OLD_SESSION_RECALL " * 100000
        RuntimeTranscriptStore(db, budget).record_command(
            event_id="e1",
            task_id="t",
            request_id="r",
            command="session_search recall old task",
            exit_code=0,
            duration_ms=1,
            stdout=huge_old_recall,
            stderr="",
        )

        assembled = RuntimePromptAssembler(db, budget).assemble(
            task_id="t",
            request_id="r",
        )

        assert assembled["ok"] is True
        assert assembled["estimated_tokens"] < 64000
        assert "truncated" in assembled["text"].lower()
        assert len(assembled["text"]) < 256000

    print("PASS Phase 15.8C Hermes session firewall verification")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
