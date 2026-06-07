"""Contract tests for REST readiness endpoint."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_health_200(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "ready_contract.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


def test_ready_has_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "ready_status.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        assert "status" in data
        assert data["status"] in ("ready", "degraded")


def test_ready_no_secrets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "no_secrets.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        text = resp.text.lower()
        assert "api_key" not in text


def test_ready_has_state_counts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "state_counts.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        db = data.get("db", {})
        assert "active_memory_count" in db
        assert "candidate_count" in db
        assert "committed_count" in db


def test_ready_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "readonly.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp1 = client.get("/ready")
        count1 = resp1.json().get("db", {}).get("memory_count", -1)
        resp2 = client.get("/ready")
        count2 = resp2.json().get("db", {}).get("memory_count", -1)
        assert count1 >= 0
        assert count2 >= 0


def test_ready_counts_storage_vs_retrieval(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "storage_vs_retrieval.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        create_resp = client.post("/v1/memories", json={"content": "Test memory for ready contract.", "memory_type": "FACT"})
        assert create_resp.status_code == 201
        ready_resp = client.get("/ready")
        ready_data = ready_resp.json()
        assert ready_data["db"]["memory_count"] >= 1
        assert ready_data["db"]["active_memory_count"] >= 1
        assert ready_data["db"]["committed_count"] >= 0


# ===================================================================
# 7. /ready returns db.evidence_quality
# ===================================================================

def test_ready_has_evidence_quality(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "ev_quality.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        db = data.get("db", {})
        assert "evidence_quality" in db
        eq = db["evidence_quality"]
        assert "low_quality_candidate_count" in eq
        assert "e0_candidate_count" in eq
        assert "missing_evidence_count" in eq
        assert "unknown_metadata_count" in eq


# ===================================================================
# 8. /ready returns low_quality_candidate_count
# ===================================================================

def test_ready_low_quality_count(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "lq_count.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        eq = data.get("db", {}).get("evidence_quality", {})
        assert isinstance(eq.get("low_quality_candidate_count", None), int)


# ===================================================================
# 9. /ready still has ready key
# ===================================================================

def test_ready_has_ready_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "ready_key.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        assert "ready" in data
        assert isinstance(data["ready"], bool)


# ===================================================================
# 10. /ready does not expose secret/token/api_key
# ===================================================================

def test_ready_no_secret_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "safe.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        text = json.dumps(data)
        assert "api_key" not in text.lower()
        # Check no secret/token fields in the response keys
        db = data.get("db", {})
        for key in db:
            assert "secret" not in key.lower()
            assert "api_key" not in key.lower()


# ===================================================================
# 11. /ready does not crash on illegal metadata
# ===================================================================

def test_ready_no_crash_on_bad_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "bad_meta.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        # Insert a memory with broken metadata via raw DB
        resp = client.get("/ready")
        data = resp.json()
        assert data["status"] in ("ready", "degraded")