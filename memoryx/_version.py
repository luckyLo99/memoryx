from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _get_version() -> str:
    version_path = Path(__file__).resolve().parent.parent / "VERSION"
    if version_path.exists():
        return version_path.read_text(encoding="utf-8").strip()

    try:
        return version("memoryx")
    except PackageNotFoundError:
        return "0+unknown"


__version__ = _get_version()
