from pathlib import Path
import json

from memoryx.release import ReleaseManifestBuilder

def test_release_manifest_written(tmp_path):
    out = tmp_path / "release_manifest.json"
    manifest = ReleaseManifestBuilder(".").build(str(out))
    assert manifest["project"] == "memoryx"
    assert manifest["version"]
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["project"] == "memoryx"

def test_dist_manifest_written(tmp_path):
    out = tmp_path / "dist_manifest.json"
    manifest = ReleaseManifestBuilder(".").dist_manifest(str(out))
    assert "files" in manifest
    assert out.exists()
