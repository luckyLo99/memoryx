from pathlib import Path

from memoryx.release import DistributionSmokeTester

def test_distribution_smoke_current_env():
    result = DistributionSmokeTester(".").import_smoke_current_env()
    assert result["ok"], result

def test_release_docs_exist():
    assert Path("docs/release_candidate.md").exists()
    assert Path("docs/trusted_publishing.md").exists()
    assert Path("docs/supply_chain.md").exists()
