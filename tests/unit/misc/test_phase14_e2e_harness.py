from pathlib import Path
import tempfile

from memoryx.e2e import E2ERuntimeHarness


def _tmp_path():
    d = tempfile.mkdtemp(dir=None)
    return Path(d)


def test_e2e_harness_generates_artifacts():
    tmp = _tmp_path()
    db = str(tmp / "harness.db")
    artifacts = str(tmp / "artifacts")

    result = E2ERuntimeHarness(db, artifacts).run_local_registry_e2e()

    assert result.ok
    assert result.claim_id
    assert result.query_result_count >= 0


def test_e2e_harness_retrieval_debug_only():
    tmp = _tmp_path()
    db = str(tmp / "harness_debug.db")
    artifacts = str(tmp / "artifacts")
    harness = E2ERuntimeHarness(db, artifacts)
    harness.run_local_registry_e2e()

    report = harness.debug_retrieval_only("concise structured")
    assert "query" in report
    assert "results" in report
