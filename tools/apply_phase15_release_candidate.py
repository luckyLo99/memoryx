from pathlib import Path
import textwrap

ROOT = Path.cwd()

def write(path: str, content: str):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")
    print(f"[WRITE] {path}")

def append_once(path: str, marker: str, content: str):
    p = ROOT / path
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    if marker in old:
        print(f"[SKIP] {path} already contains {marker}")
        return
    p.write_text(old.rstrip() + "\n\n" + textwrap.dedent(content).lstrip(), encoding="utf-8")
    print(f"[APPEND] {path}")

write("memoryx/release/__init__.py", '''
from __future__ import annotations

from .checks import ReleaseCheckResult, ReleaseChecker
from .manifest import ReleaseManifestBuilder
from .build import ReleaseBuilder
from .smoke import DistributionSmokeTester

__all__ = [
    "ReleaseCheckResult",
    "ReleaseChecker",
    "ReleaseManifestBuilder",
    "ReleaseBuilder",
    "DistributionSmokeTester",
]
''')

write("memoryx/release/checks.py", '''
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
''')

write("memoryx/release/manifest.py", '''
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

class ReleaseManifestBuilder:
    def __init__(self, root: str = "."):
        self.root = Path(root)

    def build(self, output_path: str = "release_manifest.json", include_dist: bool = True) -> dict[str, Any]:
        version = self._read_text("VERSION").strip()
        manifest: dict[str, Any] = {
            "project": "memoryx",
            "version": version,
            "python": sys.version,
            "platform": platform.platform(),
            "git": self._git_info(),
            "files": {
                "pyproject.toml": self._file_info("pyproject.toml"),
                "README.md": self._file_info("README.md"),
                "CHANGELOG.md": self._file_info("CHANGELOG.md"),
                "VERSION": self._file_info("VERSION"),
            },
            "dist": [],
        }

        if include_dist:
            dist = self.root / "dist"
            if dist.exists():
                manifest["dist"] = [
                    self._path_info(p)
                    for p in sorted(dist.iterdir())
                    if p.is_file()
                ]

        Path(output_path).write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return manifest

    def dist_manifest(self, output_path: str = "dist_manifest.json") -> dict[str, Any]:
        dist = self.root / "dist"
        files = []
        if dist.exists():
            files = [self._path_info(p) for p in sorted(dist.iterdir()) if p.is_file()]
        payload = {"files": files}
        Path(output_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload

    def _read_text(self, path: str) -> str:
        p = self.root / path
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def _file_info(self, path: str) -> dict[str, Any]:
        p = self.root / path
        if not p.exists():
            return {"exists": False}
        return self._path_info(p)

    def _path_info(self, path: Path) -> dict[str, Any]:
        data = path.read_bytes()
        return {
            "path": str(path),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def _git_info(self) -> dict[str, Any]:
        def run(args):
            try:
                proc = subprocess.run(args, cwd=self.root, capture_output=True, text=True, timeout=10)
                return proc.stdout.strip() if proc.returncode == 0 else None
            except Exception:
                return None
        return {
            "commit": run(["git", "rev-parse", "HEAD"]),
            "branch": run(["git", "rev-parse", "--abbrev-ref", "HEAD"]),
            "status_short": run(["git", "status", "--short"]),
        }
''')

write("memoryx/release/build.py", '''
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .manifest import ReleaseManifestBuilder

class ReleaseBuilder:
    def __init__(self, root: str = "."):
        self.root = Path(root)

    def clean_dist(self) -> None:
        dist = self.root / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        dist.mkdir(parents=True, exist_ok=True)

    def build(self, clean: bool = True) -> dict[str, Any]:
        if clean:
            self.clean_dist()
        cmd = [sys.executable, "-m", "build"]
        proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)
        result = {
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "dist": [],
        }
        dist = self.root / "dist"
        if dist.exists():
            result["dist"] = [str(p) for p in sorted(dist.iterdir()) if p.is_file()]
        if proc.returncode == 0:
            ReleaseManifestBuilder(str(self.root)).dist_manifest(str(self.root / "dist_manifest.json"))
        return result

    def twine_check(self) -> dict[str, Any]:
        files = sorted((self.root / "dist").glob("*"))
        if not files:
            return {"ok": False, "error": "no dist files"}
        cmd = [sys.executable, "-m", "twine", "check", *[str(p) for p in files]]
        proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)
        return {
            "ok": proc.returncode == 0,
            "cmd": cmd,
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }
''')

write("memoryx/release/smoke.py", '''
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

class DistributionSmokeTester:
    def __init__(self, root: str = "."):
        self.root = Path(root)

    def inspect_dist(self) -> dict[str, Any]:
        dist = self.root / "dist"
        files = sorted(dist.glob("*")) if dist.exists() else []
        wheels = [p for p in files if p.suffix == ".whl"]
        sdists = [p for p in files if p.name.endswith(".tar.gz")]
        return {
            "ok": bool(wheels) and bool(sdists),
            "files": [str(p) for p in files],
            "wheel_count": len(wheels),
            "sdist_count": len(sdists),
        }

    def import_smoke_current_env(self) -> dict[str, Any]:
        cmd = [sys.executable, "-c", "import memoryx; print(getattr(memoryx, '__version__', 'unknown'))"]
        proc = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        }
''')

write("memoryx/release/cli.py", '''
from __future__ import annotations

import argparse
import json

from .build import ReleaseBuilder
from .checks import ReleaseChecker
from .manifest import ReleaseManifestBuilder
from .smoke import DistributionSmokeTester

def print_json(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memoryx-release")
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status")
    sub.add_parser("build")
    sub.add_parser("verify-dist")
    sub.add_parser("manifest")
    sub.add_parser("smoke-install")

    args = p.parse_args(argv)

    if args.command == "status":
        result = ReleaseChecker(args.root).run()
        print_json(result.__dict__)
        return 0 if result.ok else 1

    if args.command == "build":
        result = ReleaseBuilder(args.root).build(clean=True)
        print_json(result)
        return 0 if result["returncode"] == 0 else result["returncode"]

    if args.command == "verify-dist":
        result = DistributionSmokeTester(args.root).inspect_dist()
        print_json(result)
        return 0 if result["ok"] else 1

    if args.command == "manifest":
        result = ReleaseManifestBuilder(args.root).build()
        print_json(result)
        return 0

    if args.command == "smoke-install":
        result = DistributionSmokeTester(args.root).import_smoke_current_env()
        print_json(result)
        return 0 if result["ok"] else 1

    raise AssertionError(args.command)

if __name__ == "__main__":
    raise SystemExit(main())
''')

write("scripts/build_release_candidate.py", '''
from __future__ import annotations

import json
import sys

from memoryx.release import ReleaseBuilder, ReleaseChecker, ReleaseManifestBuilder, DistributionSmokeTester

def main() -> int:
    checks = ReleaseChecker(".").run()
    if not checks.ok:
        print(json.dumps({"ok": False, "stage": "checks", "failures": checks.failures}, indent=2))
        return 1

    builder = ReleaseBuilder(".")
    build = builder.build(clean=True)
    if build["returncode"] != 0:
        print(json.dumps({"ok": False, "stage": "build", "build": build}, indent=2))
        return build["returncode"]

    dist = DistributionSmokeTester(".").inspect_dist()
    if not dist["ok"]:
        print(json.dumps({"ok": False, "stage": "dist", "dist": dist}, indent=2))
        return 1

    manifest = ReleaseManifestBuilder(".").build("release_manifest.json")
    dist_manifest = ReleaseManifestBuilder(".").dist_manifest("dist_manifest.json")

    print(json.dumps({
        "ok": True,
        "dist": dist,
        "manifest": "release_manifest.json",
        "dist_manifest": "dist_manifest.json",
        "version": manifest.get("version"),
    }, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
''')

write("scripts/verify_phase15_release_candidate.py", '''
from __future__ import annotations

from pathlib import Path
import json

from memoryx.release import ReleaseChecker, ReleaseManifestBuilder, DistributionSmokeTester
from memoryx.release.cli import main as release_cli

def main() -> int:
    checks = ReleaseChecker(".").run()
    assert checks.checks["version_file"]
    assert checks.checks["pyproject_exists"]
    assert checks.checks["readme_exists"]
    assert checks.checks["changelog_exists"]
    assert checks.checks["build_system_declared"]
    assert checks.checks["project_metadata_declared"]

    manifest = ReleaseManifestBuilder(".").build("release_manifest.json", include_dist=True)
    assert manifest["project"] == "memoryx"
    assert manifest["version"]

    dist_manifest = ReleaseManifestBuilder(".").dist_manifest("dist_manifest.json")
    assert "files" in dist_manifest

    smoke = DistributionSmokeTester(".").import_smoke_current_env()
    assert smoke["ok"], smoke

    assert Path(".github/workflows/memoryx-release-publish.yml").exists()
    assert Path(".github/workflows/memoryx-slsa-provenance.yml").exists()
    assert Path("docs/release_candidate.md").exists()
    assert Path("docs/trusted_publishing.md").exists()
    assert Path("docs/supply_chain.md").exists()

    assert release_cli(["status"]) == (0 if checks.ok else 1)
    assert release_cli(["manifest"]) == 0
    assert release_cli(["smoke-install"]) == 0

    print("PASS Phase 15 release candidate verification")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
''')

write(".github/workflows/memoryx-release-publish.yml", """
name: MemoryX Release Publish

on:
  workflow_dispatch:
    inputs:
      target:
        description: "Publish target"
        type: choice
        required: true
        options:
          - testpypi
          - pypi
      tag:
        description: "Expected release tag, e.g. v2.2.0"
        required: true

permissions:
  contents: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    environment: release

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install build tooling
        run: |
          python -m pip install --upgrade pip
          python -m pip install build twine
          python -m pip install -e .

      - name: Release candidate checks
        run: |
          python scripts/verify_phase15_release_candidate.py
          python -m memoryx.dev.check_release_truth
          memoryx doctor --profile lite
          pytest -q

      - name: Build distributions
        run: |
          python -m build
          python -m twine check dist/*

      - name: Generate manifests
        run: |
          python -m memoryx.release.cli manifest
          python - <<'PY'
          from memoryx.release import ReleaseManifestBuilder
          ReleaseManifestBuilder(".").dist_manifest("dist_manifest.json")
          PY

      - name: Upload release artifacts
        uses: actions/upload-artifact@v4
        with:
          name: memoryx-release-artifacts
          path: |
            dist/*
            release_manifest.json
            dist_manifest.json

      - name: Publish to TestPyPI
        if: ${{ github.event.inputs.target == 'testpypi' }}
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          repository-url: https://test.pypi.org/legacy/

      - name: Publish to PyPI
        if: ${{ github.event.inputs.target == 'pypi' && startsWith(github.event.inputs.tag, 'v') }}
        uses: pypa/gh-action-pypi-publish@release/v1
""")

write(".github/workflows/memoryx-slsa-provenance.yml", """
name: MemoryX SLSA Provenance

on:
  workflow_dispatch:

permissions:
  contents: read
  actions: read
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      hashes: ${{ steps.hash.outputs.hashes }}

    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Build distributions
        run: |
          python -m pip install --upgrade pip
          python -m pip install build
          python -m build

      - name: Generate subject hashes
        id: hash
        shell: bash
        run: |
          set -euo pipefail
          echo "hashes=$(sha256sum dist/* | base64 -w0)" >> "$GITHUB_OUTPUT"

      - name: Upload dist artifact
        uses: actions/upload-artifact@v4
        with:
          name: memoryx-dist-for-provenance
          path: dist/*
""")

write("docs/release_candidate.md", """
# Release Candidate

Phase 15 validates MemoryX release candidate readiness.

## Local verification

```bash
python scripts/verify_phase15_release_candidate.py
python scripts/build_release_candidate.py
```

## Build

```bash
python -m pip install build twine
python -m build
python -m twine check dist/*
```

## Manifest

```bash
python -m memoryx.release.cli manifest
```

Generated files:

* `release_manifest.json`
* `dist_manifest.json`
""")

write("docs/trusted_publishing.md", """
# Trusted Publishing

MemoryX release publishing is designed for PyPI Trusted Publishing through GitHub Actions OIDC.

## Workflow

```text
GitHub Actions -> OIDC token -> PyPI trusted publisher -> package upload
```

## Required PyPI configuration

Configure the PyPI project trusted publisher with:

* owner
* repository
* workflow name: `memoryx-release-publish.yml`
* optional environment: `release`

## Safety

The workflow is `workflow_dispatch` only and requires a target:

* `testpypi`
* `pypi`
""")

write("docs/supply_chain.md", """
# Supply Chain

Phase 15 adds release candidate supply-chain artifacts.

## Artifacts

* wheel
* sdist
* release manifest
* dist manifest
* SHA256 checksums
* optional SLSA provenance workflow

## Verification

```bash
python scripts/verify_phase15_release_candidate.py
python -m memoryx.release.cli verify-dist
```

## Provenance

The SLSA workflow is optional and manual. It is prepared so maintainers can attach provenance to release artifacts.
""")

append_once("mkdocs.yml", "  - Release Candidate: release_candidate.md", """
* Release Candidate: release_candidate.md
* Trusted Publishing: trusted_publishing.md
* Supply Chain: supply_chain.md
""")

append_once("RELEASE_CHECKLIST.md", "## Phase 15 Release Candidate Gate", """
## Phase 15 Release Candidate Gate

```bash
python scripts/verify_phase15_release_candidate.py
python scripts/build_release_candidate.py
python -m twine check dist/*
python -m memoryx.release.cli manifest
```

Required artifacts:

* `dist/*.whl`
* `dist/*.tar.gz`
* `release_manifest.json`
* `dist_manifest.json`
""")

append_once("CHANGELOG.md", "## [2.2.0] - Phase 15 Release Candidate Draft", """
## [2.2.0] - Phase 15 Release Candidate Draft

### Added

* Release candidate checker and CLI.
* Distribution manifest and release manifest generation.
* GitHub Actions trusted publishing workflow.
* Optional SLSA provenance workflow scaffold.
* Release candidate, trusted publishing, and supply-chain documentation.
""")

write("tests/test_release_checks.py", '''
from memoryx.release import ReleaseChecker

def test_release_checker_basic():
    result = ReleaseChecker(".").run()
    assert result.checks["version_file"]
    assert result.checks["pyproject_exists"]
    assert result.checks["readme_exists"]
    assert result.checks["changelog_exists"]
    assert result.checks["build_system_declared"]
    assert result.checks["project_metadata_declared"]
''')

write("tests/test_release_manifest.py", '''
from pathlib import Path
import json

from memoryx.release import ReleaseManifestBuilder

def test_release_manifest_written(tmp_path):
    out = tmp_path / "release_manifest.json"
    manifest = ReleaseManifestBuilder(".").build(str(out))
    assert manifest["project"] == "memoryx"
    assert manifest["version"]
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["project"] == "memoryx"

def test_dist_manifest_written(tmp_path):
    out = tmp_path / "dist_manifest.json"
    manifest = ReleaseManifestBuilder(".").dist_manifest(str(out))
    assert "files" in manifest
    assert out.exists()
''')

write("tests/test_release_workflows_static.py", '''
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
''')

write("tests/test_release_cli.py", '''
from memoryx.release.cli import main

def test_release_cli_status_manifest_smoke():
    status = main(["status"])
    assert status in {0, 1}
    assert main(["manifest"]) == 0
    assert main(["smoke-install"]) == 0
''')

write("tests/test_release_smoke_static.py", '''
from pathlib import Path

from memoryx.release import DistributionSmokeTester

def test_distribution_smoke_current_env():
    result = DistributionSmokeTester(".").import_smoke_current_env()
    assert result["ok"], result

def test_release_docs_exist():
    assert Path("docs/release_candidate.md").exists()
    assert Path("docs/trusted_publishing.md").exists()
    assert Path("docs/supply_chain.md").exists()
''')

print("[DONE] Phase 15 release candidate files written.")
print("Next:")
print("  python3 scripts/verify_phase15_release_candidate.py")
print("  pytest -q tests/test_release_checks.py tests/test_release_manifest.py tests/test_release_workflows_static.py tests/test_release_cli.py tests/test_release_smoke_static.py")
print("  python3 scripts/build_release_candidate.py")
print("  python3 -m twine check dist/*")
print("  pytest -q")
