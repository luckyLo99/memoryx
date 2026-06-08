from memoryx.release.cli import main
from pathlib import Path

def test_release_cli_status_manifest_smoke():
    manifest_path = Path("release_manifest.json")
    original = manifest_path.read_bytes() if manifest_path.exists() else None

    status = main(["status"])
    assert status in {0, 1}
    try:
        assert main(["manifest"]) == 0
        assert main(["smoke-install"]) == 0
    finally:
        if original is None:
            manifest_path.unlink(missing_ok=True)
        else:
            manifest_path.write_bytes(original)
