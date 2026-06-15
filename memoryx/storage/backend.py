"""Storage backend abstraction for MemoryX.

Supports pluggable relational storage backends:
- SQLite (default, local, single-node)
- PostgreSQL (production, high-concurrency, distributed-ready)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator


class StorageBackend(ABC):
    """Abstract interface for relational storage backends."""

    @abstractmethod
    async def open(self) -> None:
        """Initialize the backend (create pool, open connection, etc.)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Gracefully shut down the backend."""
        ...

    @abstractmethod
    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[Any, None]:
        """Acquire a connection for read-only operations."""
        ...

    @abstractmethod
    @asynccontextmanager
    async def transaction(self, mode: str = "DEFERRED") -> AsyncGenerator[Any, None]:
        """Acquire a connection within a transaction.

        Args:
            mode: Transaction mode (DEFERRED, IMMEDIATE, EXCLUSIVE for SQLite;
                or isolation level hints for PostgreSQL).
        """
        ...

    @abstractmethod
    async def execute(self, sql: str, parameters: tuple | dict | None = None) -> Any:
        """Execute a single statement (fire-and-forget)."""
        ...

    @abstractmethod
    async def fetchone(self, sql: str, parameters: tuple | dict | None = None) -> Any:
        """Execute and return the first row."""
        ...

    @abstractmethod
    async def fetchall(self, sql: str, parameters: tuple | dict | None = None) -> list[Any]:
        """Execute and return all rows."""
        ...

    @abstractmethod
    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the current schema."""
        ...

    @abstractmethod
    def _require_conn(self) -> Any:
        """Return the current thread-local connection (for batch operations)."""
        ...


class BackendFactory:
    """Factory to create the appropriate storage backend from settings."""

    @staticmethod
    def from_settings() -> StorageBackend:
        """Create a backend based on current MemoryXSettings.

        Default: SQLite. If ``database_url`` starts with ``postgresql://``,
        returns PostgreSQLBackend (requires ``asyncpg``).
        """
        from memoryx.config import get_settings
        settings = get_settings()
        db_url = getattr(settings, "database_url", None)

        if db_url and db_url.startswith("postgresql://"):
            return PostgreSQLBackend(db_url)

        # Default: SQLite
        return SQLiteBackend(settings.db_path)


# Delayed imports to avoid circular deps and optional deps

class SQLiteBackend(StorageBackend):
    """SQLite implementation using AsyncSQLite."""

    def __init__(self, db_path: Any) -> None:
        from .sqlite_async import AsyncSQLite
        self.db = AsyncSQLite(db_path)

    async def open(self) -> None:
        await self.db.open()

    async def close(self) -> None:
        await self.db.close()

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[Any, None]:
        async with self.db.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self, mode: str = "DEFERRED") -> AsyncGenerator[Any, None]:
        async with self.db.transaction(mode=mode) as conn:
            yield conn

    async def execute(self, sql: str, parameters: tuple | dict | None = None) -> Any:
        return await self.db.execute(sql, parameters)

    async def fetchone(self, sql: str, parameters: tuple | dict | None = None) -> Any:
        return await self.db.fetchone(sql, parameters)

    async def fetchall(self, sql: str, parameters: tuple | dict | None = None) -> list[Any]:
        return await self.db.fetchall(sql, parameters)

    async def table_exists(self, table_name: str) -> bool:
        return await self.db.table_exists(table_name)

    def _require_conn(self) -> Any:
        return self.db._require_conn()


class PostgreSQLBackend(StorageBackend):
    """PostgreSQL implementation (requires ``asyncpg``).

    This is a placeholder scaffold. Full implementation would map
    SQLite parameter styles (``?`` and ``:name``) to PostgreSQL
    ``$1..$N`` style and handle connection pooling via ``asyncpg.Pool``.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self._pool: Any | None = None

    async def open(self) -> None:
        try:
            import asyncpg
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL backend requires 'asyncpg'. Install with: pip install asyncpg"
            ) from exc
        self._pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=10)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[Any, None]:
        if self._pool is None:
            raise RuntimeError("PostgreSQL backend not opened. Call open() first.")
        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self, mode: str = "DEFERRED") -> AsyncGenerator[Any, None]:
        if self._pool is None:
            raise RuntimeError("PostgreSQL backend not opened. Call open() first.")
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def execute(self, sql: str, parameters: tuple | dict | None = None) -> Any:
        async with self.acquire() as conn:
            return await conn.execute(sql, *self._normalize_params(parameters))

    async def fetchone(self, sql: str, parameters: tuple | dict | None = None) -> Any:
        async with self.acquire() as conn:
            return await conn.fetchrow(sql, *self._normalize_params(parameters))

    async def fetchall(self, sql: str, parameters: tuple | dict | None = None) -> list[Any]:
        async with self.acquire() as conn:
            return await conn.fetch(sql, *self._normalize_params(parameters))

    async def table_exists(self, table_name: str) -> bool:
        row = await self.fetchone(
            "SELECT 1 FROM information_schema.tables WHERE table_name = $1",
            (table_name,),
        )
        return row is not None

    def _require_conn(self) -> Any:
        raise NotImplementedError("PostgreSQL backend does not support _require_conn; use acquire() or transaction()")

    @staticmethod
    def _normalize_params(parameters: tuple | dict | None) -> tuple:
        if parameters is None:
            return ()
        if isinstance(parameters, dict):
            return tuple(parameters.values())
        return parameters
