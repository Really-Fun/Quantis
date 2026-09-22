"""Синхронный доступ к SQLite для вызова из thread pool (не блокирует Qt/qasync)."""

from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any

from quantis.utils import app_paths

# Между сохранениями прогресса не больше этого (тики 5–20 с).
# Отсекает перемотку в конец, которая иначе засчитывала бы весь микс.
_MAX_PLAY_DELTA_MS = 45_000
# Скачок ползунка больше часов+slack считается перемоткой, не эфиром.
_SEEK_SLACK_MS = 2_500
# Старые записи: listen_count × duration. Миксы 12–24 ч раздували «эфир».
_LEGACY_LISTEN_CAP_MS = 20 * 60 * 1000
_schema_lock = threading.Lock()
# Переход в WAL берёт эксклюзивную блокировку: параллельные подключения к
# ещё не переведённой базе ловили «database is locked». WAL хранится в самом
# файле, так что переключаем один раз на путь и под замком.
_wal_lock = threading.Lock()
_wal_ready: set[str] = set()


@dataclass(frozen=True, slots=True)
class ListeningSummary:
    unique_tracks: int = 0
    total_listens: int = 0
    listened_ms: int = 0
    top_artist: str = ""
    top_artist_listens: int = 0


def default_db_path() -> Path:
    """Путь к базе в каталоге пользовательских данных."""
    return app_paths.database_path()


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = db_path or default_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path.as_posix())
    conn.row_factory = sqlite3.Row
    _ensure_wal(conn, db_path.as_posix())
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA cache_size=-8000;")
    return conn


def _ensure_wal(conn: sqlite3.Connection, key: str) -> None:
    if key in _wal_ready:
        return
    with _wal_lock:
        if key in _wal_ready:
            return
        conn.execute("PRAGMA journal_mode=WAL;")
        _wal_ready.add(key)


def ensure_schema(conn: sqlite3.Connection) -> None:
    with _schema_lock:
        _ensure_schema_locked(conn)


def _ensure_schema_locked(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS track_history (
            track_key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            source TEXT NOT NULL,
            position_ms INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            listen_count INTEGER NOT NULL DEFAULT 0,
            last_played_at INTEGER NOT NULL,
            played_ms INTEGER NOT NULL DEFAULT 0
        );
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_track_history_last_played
        ON track_history(last_played_at DESC);
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_track_history_listen_count
        ON track_history(listen_count DESC);
        """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS liked_tracks (
            track_key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            source TEXT NOT NULL,
            liked_at INTEGER NOT NULL
        );
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_liked_tracks_liked_at
        ON liked_tracks(liked_at DESC);
        """)
    _ensure_played_ms_column(conn)
    conn.commit()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    names: set[str] = set()
    for row in rows:
        name = row["name"] if isinstance(row, sqlite3.Row) else row[1]
        names.add(str(name))
    return names


def _ensure_played_ms_column(conn: sqlite3.Connection) -> None:
    if "played_ms" in _table_columns(conn, "track_history"):
        return
    try:
        conn.execute(
            "ALTER TABLE track_history ADD COLUMN played_ms INTEGER NOT NULL DEFAULT 0;"
        )
    except sqlite3.OperationalError as exc:
        if "duplicate column" not in str(exc).lower():
            raise
        return
    conn.execute(
        """
        UPDATE track_history
        SET played_ms = listen_count * CASE
            WHEN duration_ms <= 0 THEN 0
            WHEN duration_ms > ? THEN ?
            ELSE duration_ms
        END
        WHERE listen_count > 0;
        """,
        (_LEGACY_LISTEN_CAP_MS, _LEGACY_LISTEN_CAP_MS),
    )


def fetch_liked_entries(db_path: Path | None = None) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        ensure_schema(conn)
        cursor = conn.execute("""
            SELECT track_key, title, author, source, liked_at
            FROM liked_tracks
            ORDER BY liked_at DESC;
            """)
        return [dict(row) for row in cursor.fetchall()]


def is_track_liked(track_key: str, db_path: Path | None = None) -> bool:
    with _connect(db_path) as conn:
        ensure_schema(conn)
        cursor = conn.execute(
            "SELECT 1 FROM liked_tracks WHERE track_key = ? LIMIT 1;",
            (track_key,),
        )
        return cursor.fetchone() is not None


def set_track_liked(
    *,
    track_key: str,
    title: str,
    author: str,
    source: str,
    liked: bool,
    db_path: Path | None = None,
) -> None:
    with _connect(db_path) as conn:
        ensure_schema(conn)
        if liked:
            conn.execute(
                """
                INSERT INTO liked_tracks (track_key, title, author, source, liked_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(track_key) DO UPDATE SET
                    title = excluded.title,
                    author = excluded.author,
                    source = excluded.source,
                    liked_at = excluded.liked_at;
                """,
                (track_key, title, author, source, int(time())),
            )
        else:
            conn.execute(
                "DELETE FROM liked_tracks WHERE track_key = ?;",
                (track_key,),
            )
        conn.commit()


def fetch_recent_entries(
    limit: int,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    with _connect(db_path) as conn:
        ensure_schema(conn)
        cursor = conn.execute(
            """
            SELECT track_key, title, author, source, position_ms, duration_ms,
                   listen_count, last_played_at
            FROM track_history
            ORDER BY last_played_at DESC
            LIMIT ?;
            """,
            (max(1, limit),),
        )
        return [dict(row) for row in cursor.fetchall()]


def fetch_listening_summary(db_path: Path | None = None) -> ListeningSummary:
    with _connect(db_path) as conn:
        ensure_schema(conn)
        totals = conn.execute("""
            SELECT COUNT(*) AS unique_tracks,
                   COALESCE(SUM(listen_count), 0) AS total_listens,
                   COALESCE(SUM(played_ms), 0) AS listened_ms
            FROM track_history;
            """).fetchone()
        artist = conn.execute("""
            SELECT author, SUM(listen_count) AS listens
            FROM track_history
            WHERE trim(author) != ''
            GROUP BY author
            ORDER BY listens DESC, author ASC
            LIMIT 1;
            """).fetchone()
        return ListeningSummary(
            unique_tracks=int(totals["unique_tracks"] or 0),
            total_listens=int(totals["total_listens"] or 0),
            listened_ms=int(totals["listened_ms"] or 0),
            top_artist=str(artist["author"]) if artist else "",
            top_artist_listens=int(artist["listens"]) if artist else 0,
        )


def fetch_ranked_entries(
    limit: int,
    *,
    descending: bool = True,
    min_listens: int = 1,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    order = "DESC" if descending else "ASC"
    with _connect(db_path) as conn:
        ensure_schema(conn)
        cursor = conn.execute(
            f"""
            SELECT track_key, title, author, source, position_ms, duration_ms,
                   listen_count, last_played_at
            FROM track_history
            WHERE listen_count >= ?
            ORDER BY listen_count {order}, last_played_at DESC
            LIMIT ?;
            """,
            (max(0, min_listens), max(1, limit)),
        )
        return [dict(row) for row in cursor.fetchall()]


def listen_delta_ms(
    *,
    wall_ms: int,
    position_ms: int,
    last_position_ms: int,
    duration_ms: int = 0,
    interval_cap_ms: int = 8_000,
) -> int:
    """Эфир за один интервал: часы + ползунок, без зачёта перемотки.

    * Ползунок едет примерно как часы — берём согласованный ход (обычно max).
    * Ползунок завис или duration неизвестен — доверяем часам.
    * Скачок вперёд сильно больше часов — перемотка, в эфир только часы.
    * Назад — повторное прослушивание, снова только часы.
    """
    wall = max(0, int(wall_ms))
    if wall <= 0:
        return 0
    pos = max(0, int(position_ms))
    last = max(0, int(last_position_ms))
    cap = max(1, int(interval_cap_ms))
    duration = max(0, int(duration_ms))
    if duration > 0:
        cap = min(cap, duration)
        pos = min(pos, duration)
    cap = min(cap, _MAX_PLAY_DELTA_MS)

    forward = max(0, pos - last)
    if 0 < forward <= wall + _SEEK_SLACK_MS:
        add = max(wall, forward)
    else:
        add = wall
    return max(0, min(add, cap))


def get_saved_position(track_key: str, db_path: Path | None = None) -> int:
    with _connect(db_path) as conn:
        ensure_schema(conn)
        cursor = conn.execute(
            "SELECT position_ms FROM track_history WHERE track_key = ?;",
            (track_key,),
        )
        row = cursor.fetchone()
        return int(row["position_ms"]) if row is not None else 0


def upsert_progress(
    *,
    track_key: str,
    title: str,
    author: str,
    source: str,
    position_ms: int,
    duration_ms: int,
    listen_increment: int = 0,
    played_delta_ms: int | None = None,
    db_path: Path | None = None,
) -> None:
    with _connect(db_path) as conn:
        ensure_schema(conn)
        position = max(0, int(position_ms))
        duration = max(0, int(duration_ms))
        increment = max(0, int(listen_increment))
        explicit_delta = played_delta_ms is not None
        add = (
            max(0, min(int(played_delta_ms), _MAX_PLAY_DELTA_MS))
            if explicit_delta
            else 0
        )
        initial_played = add
        if not explicit_delta:
            initial_played = 0
            if increment > 0:
                initial_played = position if duration <= 0 else min(position, duration)
        if explicit_delta:
            conn.execute(
                """
                INSERT INTO track_history (
                    track_key, title, author, source, position_ms, duration_ms,
                    listen_count, last_played_at, played_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_key) DO UPDATE SET
                    title = excluded.title,
                    author = excluded.author,
                    source = excluded.source,
                    played_ms = track_history.played_ms + ?,
                    position_ms = excluded.position_ms,
                    duration_ms = CASE
                        WHEN excluded.duration_ms > 0 THEN excluded.duration_ms
                        ELSE track_history.duration_ms
                    END,
                    listen_count = track_history.listen_count + excluded.listen_count,
                    last_played_at = excluded.last_played_at;
                """,
                (
                    track_key,
                    title,
                    author,
                    source,
                    position,
                    duration,
                    increment,
                    int(time()),
                    initial_played,
                    add,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO track_history (
                    track_key, title, author, source, position_ms, duration_ms,
                    listen_count, last_played_at, played_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_key) DO UPDATE SET
                    title = excluded.title,
                    author = excluded.author,
                    source = excluded.source,
                    played_ms = track_history.played_ms + MAX(
                        0,
                        MIN(
                            excluded.position_ms - track_history.position_ms,
                            ?
                        )
                    ),
                    position_ms = excluded.position_ms,
                    duration_ms = CASE
                        WHEN excluded.duration_ms > 0 THEN excluded.duration_ms
                        ELSE track_history.duration_ms
                    END,
                    listen_count = track_history.listen_count + excluded.listen_count,
                    last_played_at = excluded.last_played_at;
                """,
                (
                    track_key,
                    title,
                    author,
                    source,
                    position,
                    duration,
                    increment,
                    int(time()),
                    initial_played,
                    _MAX_PLAY_DELTA_MS,
                ),
            )
        conn.commit()
