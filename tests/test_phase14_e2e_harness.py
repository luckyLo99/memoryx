from pathlib import Path
import zipfile

from memoryx.e2e import E2ERuntimeHarness

def test_e2e_harness_generates_artifacts(tmp_path):
    db = str(tmp_path / "harness.db")
    artifacts = str(tmp_path / "artifacts")

    result = E2ERuntimeHarness(db, artifacts).run_local_registry_e2e()

    assert result.ok
    assert result.claim_id
    assert result.query_result_count >= 1

    for path in result.artifacts.values():
        assert Path(path).exists()

    assert zipfile.is_zipfile(result.artifacts["diagnostics"])

def test_e2e_harness_retrieval_debug_only(tmp_path):
    db = str(tmp_path / "harness_debug.db")
    artifacts = str(tmp_path / "artifacts")
    harness = E2ERuntimeHarness(db, artifacts)
    harness.run_local_registry_e2e()

    report = harness.debug_retrieval_only("concise structured")
    assert "raw_fts_candidates" in report
    assert "final_results" in report
