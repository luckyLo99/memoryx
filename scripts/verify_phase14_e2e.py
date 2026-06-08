from __future__ import annotations

from pathlib import Path
import tempfile
import zipfile

from memoryx.e2e import E2ERuntimeHarness

def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        db = str(root / "phase14.db")
        artifacts = root / "artifacts"

        result = E2ERuntimeHarness(db, str(artifacts)).run_local_registry_e2e()

        assert result.ok
        assert result.claim_id
        assert result.query_result_count >= 1
        assert result.retrieval_event_count >= 1

        for name, path in result.artifacts.items():
            assert Path(path).exists(), f"missing artifact {name}: {path}"

        assert zipfile.is_zipfile(result.artifacts["diagnostics"])
        assert result.trace["request_id"] == "e2e-request"
        assert result.trace["session_id"] == "e2e-session"

    print("PASS Phase 14 E2E verification")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
