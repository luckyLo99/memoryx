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
