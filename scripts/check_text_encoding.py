from __future__ import annotations

import subprocess
import sys
from pathlib import Path


TEXT_SUFFIXES = {".md", ".py", ".toml", ".json", ".yml", ".yaml"}
MOJIBAKE_MARKERS = (
    "\u9225",
    "\u9241",
    "\u9429",
    "\u7edb",
    "\u9366",
    "\u6d93",
    "\u59af",
    "\u6d7c",
    "\u7487",
    "\u93b4",
    "\u690b",
    "\u704f",
    "\u701b",
    "\u95bf",
    "\ufffd",
    "\u0431\u043a",
    "\u00e2\u20ac",
)


def tracked_files(root: Path) -> list[Path]:
    proc = subprocess.run(
        ["git", "-C", str(root), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [
        root / line
        for line in proc.stdout.splitlines()
        if Path(line).suffix.lower() in TEXT_SUFFIXES
    ]


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    failures: list[str] = []

    for path in tracked_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            failures.append(f"{path}: not valid UTF-8: {exc}")
            continue

        for line_no, line in enumerate(text.splitlines(), 1):
            if any(marker in line for marker in MOJIBAKE_MARKERS):
                failures.append(f"{path}:{line_no}: possible mojibake: {line.strip()}")

    if failures:
        print("\n".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
