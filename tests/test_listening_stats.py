"""Тесты агрегатов статистики прослушивания."""

from __future__ import annotations

from pathlib import Path

from quantis.database.sync_history import (
    fetch_listening_summary,
    fetch_ranked_entries,
    listen_delta_ms,
    upsert_progress,
)
from quantis.ui.views.stats_page import _format_span

_STEP_MS = 30_000


def _upsert(
    db: Path,
    *,
    key: str,
    title: str,
    author: str,
    position_ms: int,
    duration_ms: int,
    listen_increment: int = 0,
    source: str = "yandex",
) -> None:
    upsert_progress(
        track_key=key,
        title=title,
        author=author,
        source=source,
        position_ms=position_ms,
        duration_ms=duration_ms,
        listen_increment=listen_increment,
        db_path=db,
    )


def _play(
    db: Path,
    *,
    key: str,
    title: str,
    author: str,
    listens: int,
    duration_ms: int = 180_000,
) -> None:
    if listens <= 0:
        _upsert(
            db,
            key=key,
            title=title,
            author=author,
            position_ms=0,
            duration_ms=duration_ms,
        )
        return
    for _ in range(listens):
        pos = 0
        _upsert(
            db,
            key=key,
            title=title,
            author=author,
            position_ms=0,
            duration_ms=duration_ms,
        )
        while pos < duration_ms:
            pos = min(duration_ms, pos + _STEP_MS)
            _upsert(
                db,
                key=key,
                title=title,
                author=author,
                position_ms=pos,
                duration_ms=duration_ms,
                listen_increment=1 if pos >= duration_ms else 0,
            )


def test_listening_summary_and_rankings(tmp_path: Path) -> None:
    db = tmp_path / "player_history.db"
    _play(db, key="yandex:1", title="Hit", author="Star", listens=5)
    _play(db, key="yandex:2", title="Rare", author="Star", listens=1)
    _play(
        db, key="yandex:3", title="Skip", author="Other", listens=0, duration_ms=60_000
    )
    _play(
        db, key="youtube:ab", title="Mix", author="DJ", listens=3, duration_ms=3_600_000
    )

    summary = fetch_listening_summary(db)
    assert summary.unique_tracks == 4
    assert summary.total_listens == 9
    assert summary.top_artist == "Star"
    assert summary.top_artist_listens == 6
    assert summary.listened_ms == 5 * 180_000 + 1 * 180_000 + 3 * 3_600_000

    most = fetch_ranked_entries(2, descending=True, db_path=db)
    assert [row["title"] for row in most] == ["Hit", "Mix"]
    assert most[0]["listen_count"] == 5

    least = fetch_ranked_entries(2, descending=False, db_path=db)
    assert [row["title"] for row in least] == ["Rare", "Mix"]


def test_empty_history_summary(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    summary = fetch_listening_summary(db)
    assert summary.unique_tracks == 0
    assert summary.total_listens == 0
    assert summary.top_artist == ""
    assert fetch_ranked_entries(5, db_path=db) == []


def test_airtime_ignores_duration_jumps_on_long_mix(tmp_path: Path) -> None:
    """Длительность микса 12ч↔24ч не должна менять уже накопленный эфир."""
    db = tmp_path / "mix.db"
    twelve_h = 12 * 3_600_000
    twenty_four_h = 24 * 3_600_000
    _upsert(
        db,
        key="youtube:mix",
        title="Mix",
        author="DJ",
        position_ms=0,
        duration_ms=twelve_h,
    )
    _upsert(
        db,
        key="youtube:mix",
        title="Mix",
        author="DJ",
        position_ms=30_000,
        duration_ms=twelve_h,
        listen_increment=1,
    )
    after_listen = fetch_listening_summary(db).listened_ms
    assert after_listen == 30_000

    _upsert(
        db,
        key="youtube:mix",
        title="Mix",
        author="DJ",
        position_ms=30_000,
        duration_ms=twenty_four_h,
    )
    assert fetch_listening_summary(db).listened_ms == 30_000


def test_seek_to_end_does_not_add_full_duration(tmp_path: Path) -> None:
    db = tmp_path / "seek.db"
    duration = 3_600_000
    _upsert(
        db,
        key="youtube:mix",
        title="Mix",
        author="DJ",
        position_ms=0,
        duration_ms=duration,
    )
    _upsert(
        db,
        key="youtube:mix",
        title="Mix",
        author="DJ",
        position_ms=duration,
        duration_ms=duration,
        listen_increment=1,
    )
    assert fetch_listening_summary(db).listened_ms == 45_000


def test_zero_duration_does_not_wipe_known_length(tmp_path: Path) -> None:
    db = tmp_path / "dur.db"
    _upsert(
        db,
        key="yandex:1",
        title="Hit",
        author="A",
        position_ms=1_000,
        duration_ms=180_000,
    )
    _upsert(
        db,
        key="yandex:1",
        title="Hit",
        author="A",
        position_ms=2_000,
        duration_ms=0,
    )
    rows = fetch_ranked_entries(1, min_listens=0, db_path=db)
    assert rows[0]["duration_ms"] == 180_000


def test_legacy_schema_migration_is_idempotent_under_concurrency(
    tmp_path: Path,
) -> None:
    import sqlite3
    from concurrent.futures import ThreadPoolExecutor, as_completed

    db = tmp_path / "legacy_race.db"
    conn = sqlite3.connect(db.as_posix())
    conn.execute("""
        CREATE TABLE track_history (
            track_key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            source TEXT NOT NULL,
            position_ms INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            listen_count INTEGER NOT NULL DEFAULT 0,
            last_played_at INTEGER NOT NULL
        );
        """)
    conn.execute(
        """
        INSERT INTO track_history
        VALUES ('youtube:mix', 'Mix', 'DJ', 'youtube', 0, ?, 1, 0);
        """,
        (12 * 3_600_000,),
    )
    conn.commit()
    conn.close()

    def load(_: int) -> int:
        return fetch_listening_summary(db).listened_ms

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(load, i) for i in range(16)]
        results = [future.result() for future in as_completed(futures)]

    expected = 20 * 60 * 1000
    assert results == [expected] * 16
    assert fetch_listening_summary(db).listened_ms == expected


def test_legacy_rows_cap_inflated_mix_duration(tmp_path: Path) -> None:
    import sqlite3

    db = tmp_path / "legacy.db"
    conn = sqlite3.connect(db.as_posix())
    conn.execute("""
        CREATE TABLE track_history (
            track_key TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            source TEXT NOT NULL,
            position_ms INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            listen_count INTEGER NOT NULL DEFAULT 0,
            last_played_at INTEGER NOT NULL
        );
        """)
    conn.execute(
        """
        INSERT INTO track_history
        VALUES ('youtube:mix', 'Mix', 'DJ', 'youtube', 0, ?, 1, 0);
        """,
        (12 * 3_600_000,),
    )
    conn.commit()
    conn.close()

    summary = fetch_listening_summary(db)
    assert summary.total_listens == 1
    assert summary.listened_ms == 20 * 60 * 1000


def test_format_span_keeps_hours_until_two_days() -> None:
    assert _format_span(0) == "0 мин"
    assert _format_span(59_999) == "0 мин"
    assert _format_span(120_000) == "2 мин"
    assert _format_span(12 * 3_600_000) == "12 ч"
    assert _format_span(24 * 3_600_000) == "24 ч"
    assert _format_span(36 * 3_600_000) == "36 ч"
    assert _format_span(48 * 3_600_000) == "2 д"
    assert _format_span(50 * 3_600_000) == "2 д 2 ч"


def test_wall_clock_counts_when_duration_and_position_are_zero(tmp_path: Path) -> None:
    """Плеер часто отдаёт duration=0 — эфир должен идти по реальному времени."""
    db = tmp_path / "wall.db"
    upsert_progress(
        track_key="youtube:x",
        title="Clip",
        author="A",
        source="youtube",
        position_ms=0,
        duration_ms=0,
        played_delta_ms=0,
        db_path=db,
    )
    for _ in range(36):
        upsert_progress(
            track_key="youtube:x",
            title="Clip",
            author="A",
            source="youtube",
            position_ms=0,
            duration_ms=0,
            played_delta_ms=5_000,
            db_path=db,
        )
    upsert_progress(
        track_key="youtube:x",
        title="Clip",
        author="A",
        source="youtube",
        position_ms=0,
        duration_ms=180_000,
        listen_increment=1,
        played_delta_ms=0,
        db_path=db,
    )
    summary = fetch_listening_summary(db)
    assert summary.listened_ms == 180_000
    row = fetch_ranked_entries(1, min_listens=0, db_path=db)[0]
    assert row["duration_ms"] == 180_000


def test_listen_delta_normal_playback_takes_agreed_progress() -> None:
    assert (
        listen_delta_ms(
            wall_ms=5_000,
            position_ms=15_000,
            last_position_ms=10_000,
            duration_ms=180_000,
        )
        == 5_000
    )
    assert (
        listen_delta_ms(
            wall_ms=5_000,
            position_ms=16_000,
            last_position_ms=10_000,
            duration_ms=180_000,
        )
        == 6_000
    )


def test_listen_delta_stuck_slider_uses_wall_clock() -> None:
    assert (
        listen_delta_ms(
            wall_ms=5_000,
            position_ms=0,
            last_position_ms=0,
            duration_ms=0,
        )
        == 5_000
    )


def test_listen_delta_seek_to_end_of_long_mix_uses_wall_only() -> None:
    assert (
        listen_delta_ms(
            wall_ms=2_000,
            position_ms=3_600_000,
            last_position_ms=10_000,
            duration_ms=3_600_000,
        )
        == 2_000
    )


def test_listen_delta_seek_backward_uses_wall_only() -> None:
    assert (
        listen_delta_ms(
            wall_ms=5_000,
            position_ms=1_000,
            last_position_ms=50_000,
            duration_ms=180_000,
        )
        == 5_000
    )


def test_listen_delta_paused_does_not_count_slider_moves() -> None:
    assert (
        listen_delta_ms(
            wall_ms=0,
            position_ms=15_000,
            last_position_ms=10_000,
            duration_ms=180_000,
        )
        == 0
    )


def test_catalog_duration_is_kept_when_player_reports_zero(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    upsert_progress(
        track_key="yandex:1",
        title="Hit",
        author="A",
        source="yandex",
        position_ms=1_000,
        duration_ms=180_000,
        db_path=db,
    )
    upsert_progress(
        track_key="yandex:1",
        title="Hit",
        author="A",
        source="yandex",
        position_ms=2_000,
        duration_ms=0,
        played_delta_ms=5_000,
        db_path=db,
    )
    row = fetch_ranked_entries(1, min_listens=0, db_path=db)[0]
    assert row["duration_ms"] == 180_000
    assert fetch_listening_summary(db).listened_ms == 5_000
