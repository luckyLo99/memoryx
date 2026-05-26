#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from memoryx.search.session_index import SessionSearchIndexBuilder


def main() -> int:
    db = os.getenv("MEMORYX_DB_PATH", "/home/lucky/memoryx/data/memoryx.db")
    hours = int(os.getenv("MEMORYX_SESSION_INDEX_HOURS", "72"))
    limit = int(os.getenv("MEMORYX_SESSION_INDEX_LIMIT", "500"))

    builder = SessionSearchIndexBuilder(db)
    n = builder.rebuild_recent(hours=hours, limit=limit)

    print({"ok": True, "indexed_sessions": n, "hours": hours, "limit": limit})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())