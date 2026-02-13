"""Репозиторий истории воспроизведения треков.

Содержит только SQL-операции и не зависит от UI/Player.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import time

from database.async_database import AsyncDatabase


@dataclass(slots=True)
class TrackHistoryEntry:
    """Запись истории воспроизведения трека."""

    track_key: str
    title: str
    author: str
    source: str
    position_ms: int
    duration_ms: int
    listen_count: int
    last_played_at: int


class TrackHistoryRepository:
    """Репозиторий для чтения и записи истории треков."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    async def upsert_progress(
        self,
        track_key: str,
        title: str,
        author: str,
        source: str,
        position_ms: int,
        duration_ms: int,
        listen_increment: int = 0,
    ) -> None:
        """Создает или обновляет прогресс трека.

        ``listen_increment`` увеличивает счетчик прослушиваний на указанное
        значение и используется на событии завершения трека.
        """
        await self._db.execute(
            """
            INSERT INTO track_history (
                track_key, title, author, source, position_ms, duration_ms,
                listen_count, last_played_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_key) DO UPDATE SET
                title = excluded.title,
                author = excluded.author,
                source = excluded.source,
                position_ms = excluded.position_ms,
                duration_ms = excluded.duration_ms,
                listen_count = track_history.listen_count + excluded.listen_count,
                last_played_at = excluded.last_played_at;
            """,
            (
                track_key,
                title,
                author,
                source,
                max(0, position_ms),
                max(0, duration_ms),
                max(0, listen_increment),
                int(time()),
            ),
        )

    async def get_saved_position(self, track_key: str) -> int:
        """Возвращает сохраненную позицию трека в миллисекундах."""
        row = await self._db.fetchone(
            "SELECT position_ms FROM track_history WHERE track_key = ?;",
            (track_key,),
        )
        if row is None:
            return 0
        return int(row.get("position_ms", 0))

    async def get_recent_entries(self, limit: int = 30) -> list[TrackHistoryEntry]:
        """Возвращает недавно прослушанные треки в порядке убывания времени."""
        rows = await self._db.fetchall(
            """
            SELECT track_key, title, author, source, position_ms, duration_ms,
                   listen_count, last_played_at
            FROM track_history
            ORDER BY last_played_at DESC
            LIMIT ?;
            """,
            (max(1, limit),),
        )
        return [
            TrackHistoryEntry(
                track_key=row["track_key"],
                title=row["title"],
                author=row["author"],
                source=row["source"],
                position_ms=int(row["position_ms"]),
                duration_ms=int(row["duration_ms"]),
                listen_count=int(row["listen_count"]),
                last_played_at=int(row["last_played_at"]),
            )
            for row in rows
        ]
