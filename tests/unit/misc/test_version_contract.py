"""P0: Version contract — package version matches project metadata."""

from importlib import metadata
from pathlib import Path

import memoryx

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_package_version():
    """memoryx.__version__ must match VERSION and installed metadata."""
    expected = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert memoryx.__version__ == expected
    assert metadata.version("memoryx") == expected
