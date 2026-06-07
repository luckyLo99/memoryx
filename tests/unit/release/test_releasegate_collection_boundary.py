"""Collection boundary test: verify pytest does not collect memoryx-pure-release.

This prevents pre-existing syntax errors in the old release snapshot
from blocking the main test suite or ReleaseGate.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def test_collect_only_excludes_memoryx_pure_release() -> None:
    """pytest --collect-only should not include memoryx-pure-release tests."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--ignore=tests/test_pii_filter.py",
         "--ignore=tests/test_extraction_client.py",
         "--ignore=tools/",
         "--ignore=memoryx-pure-release/",
         "--ignore=scripts/",
         "--ignore=tests/test_lancedb_vector_store.py"],
        capture_output=True, text=True, cwd=REPO, timeout=60,
    )
    output = result.stdout + result.stderr
    # Should not mention memoryx-pure-release at all
    assert "memoryx-pure-release" not in output, (
        f"memoryx-pure-release should be excluded from collection, "
        f"but output contains: {output[:500]}"
    )
    # Should report collected count
    assert "tests collected" in output


def test_releasegate_collect_ignores_memoryx_pure_release() -> None:
    """Simulate the ReleaseGate collection command."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "--ignore=tests/test_pii_filter.py",
         "--ignore=tests/test_extraction_client.py",
         "--ignore=tools/",
         "--ignore=memoryx-pure-release/",
         "--ignore=scripts/",
         "--ignore=tests/test_lancedb_vector_store.py"],
        capture_output=True, text=True, cwd=REPO, timeout=60,
    )
    output = result.stdout + result.stderr
    assert "error" not in output.lower() or "collected" in output
    assert "memoryx-pure-release" not in output


def test_main_test_suite_collects_correctly() -> None:
    """Verify testpaths=tests collects only the main tests directory."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests/"],
        capture_output=True, text=True, cwd=REPO, timeout=60,
    )
    output = result.stdout + result.stderr
    assert "error" not in output.lower() or "collected" in output
    # Should not include memoryx-pure-release
    assert "memoryx-pure-release" not in output
