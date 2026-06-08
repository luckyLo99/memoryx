from __future__ import annotations

import json
import sys

from memoryx.release import ReleaseBuilder, ReleaseChecker, ReleaseManifestBuilder, DistributionSmokeTester

def main() -> int:
    checks = ReleaseChecker(".").run()
    if not checks.ok:
        print(json.dumps({"ok": False, "stage": "checks", "failures": checks.failures}, indent=2))
        return 1

    builder = ReleaseBuilder(".")
    build = builder.build(clean=True)
    if build["returncode"] != 0:
        print(json.dumps({"ok": False, "stage": "build", "build": build}, indent=2))
        return build["returncode"]

    dist = DistributionSmokeTester(".").inspect_dist()
    if not dist["ok"]:
        print(json.dumps({"ok": False, "stage": "dist", "dist": dist}, indent=2))
        return 1

    manifest = ReleaseManifestBuilder(".").build("release_manifest.json")
    dist_manifest = ReleaseManifestBuilder(".").dist_manifest("dist_manifest.json")

    print(json.dumps({
        "ok": True,
        "dist": dist,
        "manifest": "release_manifest.json",
        "dist_manifest": "dist_manifest.json",
        "version": manifest.get("version"),
    }, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
