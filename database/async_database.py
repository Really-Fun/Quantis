"""Асинхронная обертка над SQLite для истории воспроизведения.

Модуль реализует низкоуровневый доступ к базе данных без бизнес-логики.
Для асинхронной работы используется ``aiosqlite``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Iterable

import aiosqlite


class AsyncDatabase:
    """Низкоуровневый асинхронный клиент SQLite.

    Ответственность класса:
    - лениво открыть соединение;
    - создать схему БД;
    - выполнять SQL-запросы асинхронно.
    """

    def __init__(self, db_path: str = "database/player_history.db") -> None:
        self._db_path = Path(db_path)
        self._conn: aiosqlite.Connection | None = None
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def ensure_initialized(self) -> None:
        """Гарантирует создание подключения и таблиц."""
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await self._connect_sync()
            await self._init_schema_sync()
            self._initialized = True

    async def execute(self, query: str, params: Iterable[Any] = ()) -> None:
        """Выполняет SQL-запрос без возвращаемого результата."""
        await self.ensure_initialized()
        await self._execute_sync(query, tuple(params))

    async def fetchone(self, query: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        """Возвращает одну запись в виде словаря или ``None``."""
        await self.ensure_initialized()
        return await self._fetchone_sync(query, tuple(params))

    async def fetchall(self, query: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        """Возвращает список записей в виде словарей."""
        await self.ensure_initialized()
        return await self._fetchall_sync(query, tuple(params))

    async def close(self) -> None:
        """Закрывает соединение."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _connect_sync(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._db_path.as_posix())
        self._conn.row_factory = aiosqlite.Row

        # Настройки для быстрого и безопасного режима SQLite.
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA temp_store=MEMORY;")
        await self._conn.execute("PRAGMA cache_size=-20000;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.commit()

    async def _init_schema_sync(self) -> None:
        assert self._conn is not None
        await self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS track_history (
                track_key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                source TEXT NOT NULL,
                position_ms INTEGER NOT NULL DEFAULT 0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                listen_count INTEGER NOT NULL DEFAULT 0,
                last_played_at INTEGER NOT NULL
            );
            """
        )
        await self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_track_history_last_played
            ON track_history(last_played_at DESC);
            """
        )
        await self._conn.commit()

    async def _execute_sync(self, query: str, params: tuple[Any, ...]) -> None:
        assert self._conn is not None
        await self._conn.execute(query, params)
        await self._conn.commit()

    async def _fetchone_sync(self, query: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        assert self._conn is not None
        async with self._conn.execute(query, params) as cursor:
            row = await cursor.fetchone()
        return dict(row) if row is not None else None

    async def _fetchall_sync(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        assert self._conn is not None
        async with self._conn.execute(query, params) as cursor:
            rows = await cursor.fetchall()
        return [dict(row) for row in rows]
