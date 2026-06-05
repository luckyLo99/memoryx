from __future__ import annotations

from pathlib import Path
import json

from memoryx.release import ReleaseChecker, ReleaseManifestBuilder, DistributionSmokeTester
from memoryx.release.cli import main as release_cli

def main() -> int:
    checks = ReleaseChecker(".").run()
    assert checks.checks["version_file"]
    assert checks.checks["pyproject_exists"]
    assert checks.checks["readme_exists"]
    assert checks.checks["changelog_exists"]
    assert checks.checks["build_system_declared"]
    assert checks.checks["project_metadata_declared"]

    manifest = ReleaseManifestBuilder(".").build("release_manifest.json", include_dist=True)
    assert manifest["project"] == "memoryx"
    assert manifest["version"]

    dist_manifest = ReleaseManifestBuilder(".").dist_manifest("dist_manifest.json")
    assert "files" in dist_manifest

    smoke = DistributionSmokeTester(".").import_smoke_current_env()
    assert smoke["ok"], smoke

    assert Path(".github/workflows/memoryx-release-publish.yml").exists()
    assert Path(".github/workflows/memoryx-slsa-provenance.yml").exists()
    assert Path("docs/release_candidate.md").exists()
    assert Path("docs/trusted_publishing.md").exists()
    assert Path("docs/supply_chain.md").exists()

    assert release_cli(["status"]) == (0 if checks.ok else 1)
    assert release_cli(["manifest"]) == 0
    assert release_cli(["smoke-install"]) == 0

    print("PASS Phase 15 release candidate verification")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
