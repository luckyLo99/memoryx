#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memoryx.diagnostics.replay_exporter import export_replay_jsonl_to_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a redacted MemoryX replay JSON from trace JSONL.")
    parser.add_argument("--input", required=True, help="Input redacted trace JSONL path")
    parser.add_argument("--output", required=True, help="Output replay JSON path")
    parser.add_argument("--scenario", required=True, help="Replay scenario")
    parser.add_argument("--expected", required=True, help="Expected behavior")
    parser.add_argument("--observed", required=True, help="Observed behavior")
    args = parser.parse_args(argv)

    try:
        export_replay_jsonl_to_file(args.input, args.output, args.scenario, args.expected, args.observed)
    except Exception as exc:
        print(f"replay_export: FAIL {exc}", file=sys.stderr)
        return 1
    print(f"replay_export: PASS {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
