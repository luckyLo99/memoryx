from __future__ import annotations

import asyncio
import contextvars
import sqlite3
from collections.abc import Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional


_TX_OWNER: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "memoryx_sqlite_tx_owner",
    default=False,
)


class AsyncSQLite:
    def __init__(self, db_path: Path, timeout: float = 30.0) -> None:
        self.db_path = db_path
        self.timeout = timeout
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()

    async def open(self) -> None:
        if self._conn is not None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await asyncio.to_thread(self._connect)
        await self.execute("PRAGMA journal_mode=WAL;")
        await self.execute("PRAGMA synchronous=NORMAL;")
        await self.execute("PRAGMA temp_store=MEMORY;")
        await self.execute("PRAGMA foreign_keys=ON;")
        await self.execute("PRAGMA busy_timeout=5000;")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    async def close(self) -> None:
        if self._conn is None:
            return
        conn = self._conn
        self._conn = None
        await asyncio.to_thread(conn.close)

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SQLite connection is not open")
        return self._conn

    def _execute_direct(self, sql: str, params: Iterable[Any] = ()) -> int:
        cursor = self._require_conn().execute(sql, tuple(params))
        rowcount = cursor.rowcount
        cursor.close()
        return rowcount

    def _fetchone_direct(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        cursor = self._require_conn().execute(sql, tuple(params))
        row = cursor.fetchone()
        cursor.close()
        return row

    def _fetchall_direct(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        cursor = self._require_conn().execute(sql, tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        return list(rows)

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        if _TX_OWNER.get():
            return self._execute_direct(sql, params)
        conn = self._require_conn()
        async with self._lock:
            cursor = await asyncio.to_thread(conn.execute, sql, tuple(params))
            rowcount = cursor.rowcount
            await asyncio.to_thread(cursor.close)
            return rowcount

    async def executescript(self, sql: str) -> None:
        conn = self._require_conn()
        async with self._lock:
            await asyncio.to_thread(conn.executescript, sql)

    async def executemany(self, sql: str, seq_of_params: Iterable[Iterable[Any]]) -> int:
        conn = self._require_conn()
        async with self._lock:
            cursor = await asyncio.to_thread(
                conn.executemany,
                sql,
                [tuple(params) for params in seq_of_params],
            )
            rowcount = cursor.rowcount
            await asyncio.to_thread(cursor.close)
            return rowcount

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        if _TX_OWNER.get():
            return self._fetchone_direct(sql, params)
        conn = self._require_conn()
        async with self._lock:
            cursor = await asyncio.to_thread(conn.execute, sql, tuple(params))
            row = await asyncio.to_thread(cursor.fetchone)
            await asyncio.to_thread(cursor.close)
            return row

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        if _TX_OWNER.get():
            return self._fetchall_direct(sql, params)
        conn = self._require_conn()
        async with self._lock:
            cursor = await asyncio.to_thread(conn.execute, sql, tuple(params))
            rows = await asyncio.to_thread(cursor.fetchall)
            await asyncio.to_thread(cursor.close)
            return list(rows)

    @asynccontextmanager
    async def transaction(self, mode: str = "IMMEDIATE") -> AsyncIterator[sqlite3.Connection]:
        mode_upper = (mode or "IMMEDIATE").strip().upper()
        if mode_upper not in {"IMMEDIATE", "DEFERRED", "EXCLUSIVE"}:
            raise ValueError(f"Unsupported transaction mode: {mode}")
        conn = self._require_conn()
        async with self._lock:
            token = _TX_OWNER.set(True)
            try:
                await asyncio.to_thread(conn.execute, f"BEGIN {mode_upper};")
                yield conn
            except Exception:
                await asyncio.to_thread(conn.execute, "ROLLBACK;")
                raise
            else:
                await asyncio.to_thread(conn.execute, "COMMIT;")
            finally:
                _TX_OWNER.reset(token)

    async def vacuum(self) -> None:
        await self.execute("VACUUM;")

    async def pragma(self, statement: str) -> None:
        await self.execute(f"PRAGMA {statement};")
