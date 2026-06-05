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
