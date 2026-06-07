from __future__ import annotations

import pytest

from memoryx.context_budget import TokenEstimator
from memoryx.learning.artifacts import StudyArtifactBuilder
from memoryx.skills.distiller import _safe_skill_install_root, _safe_skill_key


def test_context_budget_tokens_module_is_packaged() -> None:
    estimator = TokenEstimator()

    estimate = estimator.estimate_text("hello world")

    assert estimate.text_chars == 11
    assert estimate.estimated_tokens >= 1


def test_study_artifact_root_must_stay_inside_configured_root(tmp_path, monkeypatch) -> None:
    allowed = tmp_path / "memoryx-data"
    outside = tmp_path / "outside"
    monkeypatch.setenv("MEMORYX_ROOT", str(allowed))

    builder = StudyArtifactBuilder(allowed)

    assert builder.study_dir == allowed / "study"
    with pytest.raises(ValueError, match="artifact root"):
        StudyArtifactBuilder(outside)


def test_skill_install_root_must_stay_inside_configured_root(tmp_path, monkeypatch) -> None:
    allowed = tmp_path / "skills"
    outside = tmp_path / "outside"
    monkeypatch.setenv("HERMES_SKILL_DIR", str(allowed))
    monkeypatch.delenv("MEMORYX_ALLOWED_SKILL_DIR", raising=False)

    assert _safe_skill_install_root(allowed / "drafts") == allowed / "drafts"
    with pytest.raises(ValueError, match="skill install directory"):
        _safe_skill_install_root(outside)


def test_skill_key_sanitization_rejects_empty_keys() -> None:
    assert _safe_skill_key("memoryx/hermes operator") == "memoryx_hermes_operator"
    with pytest.raises(ValueError, match="skill key"):
        _safe_skill_key("...")
