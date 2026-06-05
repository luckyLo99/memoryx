from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from typing import Any

def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    path: str
    kind: str
    bytes: int
    sha256: str
    summary: str
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

class ArtifactStore:
    def __init__(self, root: str = ".memoryx/runtime_artifacts"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
    def write_text(self, *, kind: str, name: str, text: str, summary: str | None = None) -> ArtifactRef:
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        path = self.root / f"{utc_stamp()}_{safe}"
        path.write_text(text or "", encoding="utf-8")
        return self.ref(path, kind=kind, summary=summary)
    def ref(self, path: str | Path, *, kind: str, summary: str | None = None) -> ArtifactRef:
        p = Path(path)
        data = p.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        artifact_id = sha[:16]
        return ArtifactRef(artifact_id=artifact_id, path=str(p), kind=kind, bytes=len(data), sha256=sha, summary=summary or self._summary(p, data))
    def _summary(self, path: Path, data: bytes) -> str:
        suffix = path.suffix.lower()
        if suffix in {".patch", ".diff"}:
            text = data.decode("utf-8", errors="replace")
            lines = text.splitlines()
            added = sum(1 for x in lines if x.startswith("+") and not x.startswith("+++"))
            removed = sum(1 for x in lines if x.startswith("-") and not x.startswith("---"))
            files = sum(1 for x in lines if x.startswith("diff --git"))
            return f"{files} files, +{added}/-{removed}, {len(lines)} lines"
        return f"{path.name}, {len(data)} bytes"
