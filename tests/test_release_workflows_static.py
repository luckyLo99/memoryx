from pathlib import Path

def test_release_publish_workflow_static():
    text = Path(".github/workflows/memoryx-release-publish.yml").read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "pypa/gh-action-pypi-publish" in text
    assert "workflow_dispatch" in text
    assert "twine check" in text

def test_slsa_workflow_static():
    text = Path(".github/workflows/memoryx-slsa-provenance.yml").read_text(encoding="utf-8")
    assert "id-token: write" in text
    assert "sha256sum dist/*" in text
    assert "upload-artifact" in text
