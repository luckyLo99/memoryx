from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import subprocess
import sys
from typing import Any

@dataclass(frozen=True)
class ReleaseCheckResult:
    ok: bool
    checks: dict[str, bool]
    details: dict[str, Any] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)

class ReleaseChecker:
    def __init__(self, root: str = "."):
        self.root = Path(root)

    def run(self) -> ReleaseCheckResult:
        checks: dict[str, bool] = {}
        details: dict[str, Any] = {}
        failures: list[str] = []

        version = self.version()
        details["version"] = version

        checks["version_file"] = bool(version)
        checks["pyproject_exists"] = (self.root / "pyproject.toml").exists()
        checks["readme_exists"] = (self.root / "README.md").exists()
        checks["changelog_exists"] = (self.root / "CHANGELOG.md").exists()
        checks["license_exists"] = any((self.root / name).exists() for name in ["LICENSE", "LICENSE.md", "LICENSE.txt"])
        checks["release_checklist_exists"] = (self.root / "RELEASE_CHECKLIST.md").exists()

        pyproject = self.read("pyproject.toml")
        readme = self.read("README.md")
        changelog = self.read("CHANGELOG.md")

        checks["version_in_pyproject"] = version in pyproject if version else False
        checks["version_in_changelog"] = version in changelog if version else False
        checks["readme_mentions_memoryx"] = "MemoryX" in readme or "memoryx" in readme.lower()
        checks["build_system_declared"] = "[build-system]" in pyproject
        checks["project_metadata_declared"] = "[project]" in pyproject

        for name, ok in checks.items():
            if not ok:
                failures.append(name)

        return ReleaseCheckResult(ok=not failures, checks=checks, details=details, failures=failures)

    def version(self) -> str:
        path = self.root / "VERSION"
        return path.read_text(encoding="utf-8").strip() if path.exists() else ""

    def read(self, path: str) -> str:
        p = self.root / path
        return p.read_text(encoding="utf-8") if p.exists() else ""
