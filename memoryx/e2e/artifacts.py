from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

@dataclass(frozen=True)
class E2EArtifactBundle:
    root: Path

    def path(self, name: str) -> str:
        self.root.mkdir(parents=True, exist_ok=True)
        return str(self.root / name)

    def write_json(self, name: str, payload: Any) -> str:
        path = self.root / name
        self.root.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        return str(path)

    def exists(self, name: str) -> bool:
        return (self.root / name).exists()
