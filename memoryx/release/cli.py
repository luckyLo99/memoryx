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
