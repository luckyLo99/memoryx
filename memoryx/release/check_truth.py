#!/usr/bin/env python3
"""Release truth consistency check for MemoryX.

Usage: python -m memoryx.dev.check_release_truth
Expected output: PASS release truth consistent: <VERSION>
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    # 1. VERSION file
    version_file = REPO_ROOT / "VERSION"
    version_file_content = version_file.read_text().strip()

    # 2. memoryx/__init__.py
    from memoryx import __version__ as pkg_version

    # 3. CHANGELOG.md uses the same next version
    changelog_path = REPO_ROOT / "CHANGELOG.md"
    changelog = changelog_path.read_text()

    errors = []

    # Check 1: VERSION file matches __version__
    if version_file_content != pkg_version:
        errors.append(
            f"VERSION ({version_file_content}) != memoryx.__version__ ({pkg_version})"
        )

    # Check 2: VERSION appears in CHANGELOG header
    if f"[{version_file_content}]" not in changelog:
        errors.append(
            f"CHANGELOG.md missing header for [{version_file_content}]"
        )

    if errors:
        print("FAIL release truth inconsistent:")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(f"PASS release truth consistent: {version_file_content}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
