"""Tests for REST runtime path parity: DB path resolution."""
from __future__ import annotations

import os
from pathlib import Path

import pytest


# ===================================================================
# 1. MEMORYX_DB_PATH sets REST DB path
# ===================================================================

def test_memoryx_db_path_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", "/custom/path/memoryx.db")
    from memoryx.api.app_factory import _default_db_path
    result = _default_db_path()
    assert result == Path("/custom/path/memoryx.db")


# ===================================================================
# 2. MEMORYX_HOME sets REST DB path when MEMORYX_DB_PATH unset
# ===================================================================

def test_memoryx_home_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEMORYX_DB_PATH", raising=False)
    monkeypatch.setenv("MEMORYX_HOME", "/custom/home")
    from memoryx.api.app_factory import _default_db_path
    result = _default_db_path()
    assert result == Path("/custom/home/memoryx.db")


# ===================================================================
# 3. No env set => ./data/memoryx.db fallback
# ===================================================================

def test_fallback_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MEMORYX_DB_PATH", raising=False)
    monkeypatch.delenv("MEMORYX_HOME", raising=False)
    from memoryx.api.app_factory import _default_db_path
    result = _default_db_path()
    assert result == Path("./data/memoryx.db")


# ===================================================================
# 4. /ready returns db.path in response
# ===================================================================

def test_ready_returns_db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "test_memoryx.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        assert "db" in data
        assert "path" in data["db"]


# ===================================================================
# 5. /ready returns memory_count
# ===================================================================

def test_ready_memory_count(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "count_memoryx.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        assert "memory_count" in data.get("db", {})
        assert isinstance(data["db"]["memory_count"], int)


# ===================================================================
# 6. /ready returns cwd
# ===================================================================

def test_ready_returns_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "cwd_memoryx.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        assert "env" in data
        assert "cwd" in data["env"]
        assert "memoryx_home" in data["env"]


# ===================================================================
# 7. DB not reachable returns degraded, not crash
# ===================================================================

def test_ready_db_not_found_degraded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MEMORYX_DB_PATH", str(tmp_path / "nonexistent" / "no_memoryx.db"))
    from memoryx.api.app_factory import create_app
    from fastapi.testclient import TestClient
    app = create_app(auto_open=True)
    with TestClient(app) as client:
        resp = client.get("/ready")
        data = resp.json()
        assert "status" in data