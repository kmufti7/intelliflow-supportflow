"""SQLite async connection management."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from ..utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseConnection:
    """Async SQLite connection manager."""

    def __init__(self, db_path: str | Path):
        """Initialize the connection manager.

        Args:
            db_path: Path to the SQLite database file
        """
        self.db_path = Path(db_path)
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the database connection and create directories if needed."""
        # Ensure the directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Connect to database
        self._connection = await aiosqlite.connect(self.db_path)
        self._connection.row_factory = aiosqlite.Row

        # Enable foreign keys
        await self._connection.execute("PRAGMA foreign_keys = ON")

        logger.info("database_connected", path=str(self.db_path))

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("database_disconnected", path=str(self.db_path))

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the active connection."""
        if not self._connection:
            raise RuntimeError("Database not connected. Call initialize() first.")
        return self._connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Context manager for database transactions.

        Yields:
            The database connection within a transaction
        """
        async with self._lock:
            try:
                yield self.connection
                await self.connection.commit()
            except Exception:
                await self.connection.rollback()
                raise

    async def execute(
        self,
        sql: str,
        parameters: tuple | dict | None = None,
    ) -> aiosqlite.Cursor:
        """Execute a SQL statement.

        Args:
            sql: SQL statement to execute
            parameters: Query parameters

        Returns:
            The cursor after execution
        """
        async with self._lock:
            cursor = await self.connection.execute(sql, parameters or ())
            await self.connection.commit()
            return cursor

    async def execute_many(
        self,
        sql: str,
        parameters: list[tuple | dict],
    ) -> None:
        """Execute a SQL statement multiple times with different parameters.

        Args:
            sql: SQL statement to execute
            parameters: List of parameter tuples/dicts
        """
        async with self._lock:
            await self.connection.executemany(sql, parameters)
            await self.connection.commit()

    async def fetch_one(
        self,
        sql: str,
        parameters: tuple | dict | None = None,
    ) -> aiosqlite.Row | None:
        """Fetch a single row.

        Args:
            sql: SQL query
            parameters: Query parameters

        Returns:
            The row or None if not found
        """
        async with self._lock:
            cursor = await self.connection.execute(sql, parameters or ())
            return await cursor.fetchone()

    async def fetch_all(
        self,
        sql: str,
        parameters: tuple | dict | None = None,
    ) -> list[aiosqlite.Row]:
        """Fetch all rows.

        Args:
            sql: SQL query
            parameters: Query parameters

        Returns:
            List of rows
        """
        async with self._lock:
            cursor = await self.connection.execute(sql, parameters or ())
            return await cursor.fetchall()


# Global connection instance
_db_connection: DatabaseConnection | None = None


async def get_database(db_path: str | Path | None = None) -> DatabaseConnection:
    """Get or create the database connection.

    Args:
        db_path: Optional path to database (only used on first call)

    Returns:
        The database connection instance
    """
    global _db_connection

    if _db_connection is None:
        if db_path is None:
            from ..config import get_settings

            db_path = get_settings().database_path

        _db_connection = DatabaseConnection(db_path)
        await _db_connection.initialize()

    return _db_connection


async def close_database() -> None:
    """Close the global database connection."""
    global _db_connection

    if _db_connection:
        await _db_connection.close()
        _db_connection = None
