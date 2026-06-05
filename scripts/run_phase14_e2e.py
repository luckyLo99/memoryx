from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from memoryx.e2e import E2ERuntimeHarness

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="memoryx-phase14-e2e")
    p.add_argument("--db", default="./memoryx_phase14_e2e.db")
    p.add_argument("--artifacts", default="./phase14_artifacts")
    args = p.parse_args(argv)

    result = E2ERuntimeHarness(args.db, args.artifacts).run_local_registry_e2e()
    payload = asdict(result)

    Path(args.artifacts).mkdir(parents=True, exist_ok=True)
    summary = Path(args.artifacts) / "phase14_e2e_summary.json"
    summary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if result.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
