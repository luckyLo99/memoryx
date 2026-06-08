"""Check release manifest truth — verify that committed files match manifest hashes."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_release_truth(repo_root: Path | None = None) -> int:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent.parent
    manifest_path = repo_root / "release_manifest.json"
    if not manifest_path.exists():
        print("No release_manifest.json found — skipping verification.", file=sys.stderr)
        return 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors = 0
    for name, entry in manifest.get("files", {}).items():
        fp = repo_root / entry["path"]
        if not fp.exists():
            print(f"MISSING: {entry['path']}", file=sys.stderr)
            errors += 1
            continue
        actual = _sha256(fp)
        if actual != entry["sha256"]:
            print(f"HASH MISMATCH: {entry['path']}", file=sys.stderr)
            print(f"  expected: {entry['sha256']}", file=sys.stderr)
            print(f"  actual:   {actual}", file=sys.stderr)
            errors += 1
    if errors:
        print(f"\n{errors} file(s) differ from manifest.", file=sys.stderr)
    else:
        print("Release manifest verified: all file hashes match.")
    return errors


if __name__ == "__main__":
    sys.exit(check_release_truth())
