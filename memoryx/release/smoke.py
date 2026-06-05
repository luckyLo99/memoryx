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
