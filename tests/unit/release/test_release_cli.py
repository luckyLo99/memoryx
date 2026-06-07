from memoryx.release.cli import main

def test_release_cli_status_manifest_smoke():
    status = main(["status"])
    assert status in {0, 1}
    assert main(["manifest"]) == 0
    assert main(["smoke-install"]) == 0
