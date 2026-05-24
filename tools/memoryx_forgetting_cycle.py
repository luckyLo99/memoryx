#!/usr/bin/env python3
"""MemoryX Forgetting Cycle — archive low-trust memories, decay unverified agent memories.

Principles:
- Never delete high-trust verified user facts.
- Never delete tool-verified facts.
- Priority archive: low-trust, unverified, long-unaccessed agent inferences/reflections.
- Low-trust agent memories get gradual confidence decay instead of hard delete.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memoryx.storage import MemoryRepository


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.getenv("MEMORYX_DB_PATH", "data/memoryx.db"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = MemoryRepository(Path(args.db))
    await repo.open()

    rows = await repo.db.fetchall(
        """
        SELECT id, memory_type, content, importance_score, confidence_score,
               access_count, created_at, expires_at, source_type, verification_status
        FROM memories
        WHERE active_state IN ('active', 1)
        """
    )

    archived = 0
    decayed = 0
    now = datetime.now(timezone.utc)

    for r in rows:
        memory_id = r["id"]
        confidence = float(r["confidence_score"] or 0.5)
        access_count = int(r["access_count"] or 0)
        source_type = str(r["source_type"] or "unknown")
        verification = str(r["verification_status"] or "unverified")

        should_archive = False
        reason = ""

        # ── Expired memories ──
        if r["expires_at"]:
            try:
                exp = datetime.fromisoformat(
                    str(r["expires_at"]).replace("Z", "+00:00")
                )
                if exp < now:
                    should_archive = True
                    reason = "expired"
            except Exception:
                pass

        # ── Low-trust unverified agent memories, never accessed ──
        if (
            source_type in {"agent_inferred", "agent_reflection"}
            and verification != "verified"
        ):
            if confidence < 0.45 and access_count == 0:
                should_archive = True
                reason = "low_trust_unverified_agent_memory"

        if should_archive:
            archived += 1
            if not args.dry_run:
                await repo.db.execute(
                    "UPDATE memories SET active_state='archived', archived_at=CURRENT_TIMESTAMP WHERE id=?;",
                    (memory_id,),
                )
                await repo.db.execute(
                    """
                    INSERT INTO memory_forgetting_events(
                        id, memory_id, action, reason, old_confidence, new_confidence
                    ) VALUES (?, ?, 'archive', ?, ?, ?);
                    """,
                    (uuid4().hex, memory_id, reason, confidence, confidence),
                )
            continue

        # ── Decay unverified agent memories (gradual confidence reduction) ──
        if (
            source_type in {"agent_inferred", "agent_reflection"}
            and verification != "verified"
            and confidence > 0.1
        ):
            decayed += 1
            new_confidence = max(0.1, confidence - 0.03)
            if not args.dry_run:
                await repo.db.execute(
                    "UPDATE memories SET confidence_score=? WHERE id=?;",
                    (new_confidence, memory_id),
                )
                await repo.db.execute(
                    """
                    INSERT INTO memory_forgetting_events(
                        id, memory_id, action, reason, old_confidence, new_confidence
                    ) VALUES (?, ?, 'decay', 'unverified_agent_memory_decay', ?, ?);
                    """,
                    (uuid4().hex, memory_id, confidence, new_confidence),
                )

    await repo.close()

    result = {
        "archived": archived,
        "decayed": decayed,
        "dry_run": args.dry_run,
    }
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))