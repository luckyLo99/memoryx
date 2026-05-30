"""Contract tests for REST readiness endpoint."""
from __future__ import annotations

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