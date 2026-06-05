from pathlib import Path

from memoryx.runtime_context import PatchArtifactGuard, RuntimeContextBudget


def test_patch_guard_artifact_only(tmp_path):
    guard = PatchArtifactGuard(
        artifact_root=str(tmp_path / "artifacts"),
        budget=RuntimeContextBudget(max_inline_patch_chars=0, artifact_only_patches=True),
    )
    patch = "\n".join("+ line" for _ in range(10000))
    result = guard.store_patch(name="x.patch", patch_text=patch)

    assert result["prompt_safe"] is True
    assert result["inline_allowed"] is False
    assert result["patch_text"] == ""
    assert result["artifact"] is not None
    assert Path(result["artifact"]["path"]).exists()
