from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from memoryx.config import MIGRATIONS_DIR, SCHEMA_PATH
from .sqlite_async import AsyncSQLite

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MigrationResult:
    applied: bool
    schema_version: int


class MigrationManager:
    def __init__(self, db: AsyncSQLite, migrations_dir: Path | None = None) -> None:
        self.db = db
        self.migrations_dir = migrations_dir or MIGRATIONS_DIR

    async def ensure_schema(self) -> MigrationResult:
        await self.db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);"
        )
        row = await self.db.fetchone("SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations;")
        current = int(row["version"] if row is not None else 0)
        applied = False

        if current == 0:
            try:
                await self.db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
                await self.db.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);")
                current = 1
                applied = True
            except Exception:
                logger.exception("Failed to apply initial schema (version 1)")
                return MigrationResult(applied=False, schema_version=current)

        for version, sql in self._load_migrations():
            if version <= current:
                continue
            try:
                # Wrap each migration in a transaction for atomicity.
                # executescript commits any pending transaction first, so we
                # add BEGIN/COMMIT around the SQL to ensure atomicity.
                transactional_sql = f"BEGIN;\n{sql}\nCOMMIT;"
                await self.db.executescript(transactional_sql)
                await self.db.execute("INSERT INTO schema_migrations(version) VALUES (?);", (version,))
                current = version
                applied = True
            except Exception:
                logger.exception("Failed to apply migration version %d, stopping further migrations", version)
                break
        return MigrationResult(applied=applied, schema_version=current)

    def _load_migrations(self) -> list[tuple[int, str]]:
        items: list[tuple[int, str]] = []
        if not self.migrations_dir.exists():
            return items
        for path in sorted(self.migrations_dir.glob("*.sql")):
            stem = path.stem.split("_", 1)[0]
            try:
                version = int(stem)
            except ValueError:
                continue
            if version == 1:
                continue
            items.append((version, path.read_text(encoding="utf-8")))
        return items
