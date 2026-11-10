"""Миксы на главной, ритм и топ артистов статистики, карточка с наведением."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QMouseEvent

from quantis.database import sync_history
from quantis.models import YoutubeTrack
from quantis.services.mixes import build_mixes, plan_mixes
from quantis.utils.artists import primary_artist

_NOW = 1_800_000_000
_DAY = 24 * 3600


def _entry(key: str, author: str, listens: int, days_ago: float = 0) -> dict:
    return {
        "track_key": key,
        "title": key,
        "author": author,
        "source": "youtube",
        "duration_ms": 180_000,
        "listen_count": listens,
        "last_played_at": int(_NOW - days_ago * _DAY),
    }


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        ("Narvent, VØJ", "Narvent"),
        ("Miyagi feat. Andy Panda", "Miyagi"),
        ("The Weeknd ft Daft Punk", "The Weeknd"),
        ("Король и Шут", "Король и Шут"),
        ("Simon & Garfunkel", "Simon & Garfunkel"),
        ("Lil Nas X", "Lil Nas X"),
        ("  qxiet ", "qxiet"),
    ],
)
def test_primary_artist(author: str, expected: str) -> None:
    assert primary_artist(author) == expected


def test_plan_mixes_repeat_artists_and_forgotten() -> None:
    entries = [
        _entry("yt:a1", "Высоцкий", 9),
        _entry("yt:a2", "Высоцкий", 5),
        _entry("yt:a3", "Высоцкий, Влади", 3),
        _entry("yt:b1", "Radiohead", 4, days_ago=40),
        _entry("yt:b2", "Radiohead", 3, days_ago=35),
        _entry("yt:c1", "Solo", 2, days_ago=30),
        _entry("yt:c2", "Other", 2, days_ago=25),
        _entry("yt:z1", "Never", 0),
    ]
    specs = {spec.mix_id: spec for spec in plan_mixes(entries, now=_NOW)}

    assert specs["repeat"].keys[:2] == ("yt:a1", "yt:a2")
    assert "yt:z1" not in specs["repeat"].keys
    # «Высоцкий, Влади» — тот же первый артист.
    assert specs["artist:высоцкий"].keys == ("yt:a1", "yt:a2", "yt:a3")
    assert specs["artist:высоцкий"].name == "Высоцкий"
    # У Radiohead два трека — меньше порога, отдельного микса нет.
    assert "artist:radiohead" not in specs
    assert set(specs["forgotten"].keys) == {"yt:b1", "yt:b2", "yt:c1", "yt:c2"}


def test_plan_mixes_empty_history_gives_nothing() -> None:
    assert plan_mixes([], now=_NOW) == []
    assert plan_mixes([_entry("yt:a", "A", 1)], now=_NOW) == []


def test_liked_tracks_lift_an_artist_mix() -> None:
    entries = [_entry(f"yt:l{i}", "Liked", 0) for i in range(3)]
    entries += [_entry(f"yt:q{i}", "Quiet", 0) for i in range(3)]
    specs = plan_mixes(entries, {"yt:l0", "yt:l1"}, now=_NOW)
    assert [s.mix_id for s in specs] == ["artist:liked"]


def test_build_mixes_skips_missing_tracks() -> None:
    entries = [_entry(f"yt:t{i}", "A", 5 - i) for i in range(4)]
    specs = plan_mixes(entries, now=_NOW)
    tracks = {"yt:t0": YoutubeTrack(track_id="t0", title="t0", author="A")}
    mixes = build_mixes(specs, tracks)
    assert mixes and all(len(m.get_tracks()) == 1 for m in mixes)


# --- база: журнал, ритм, артисты ------------------------------------------


def _finish(db: Path, key: str, author: str, times: int = 1) -> None:
    sync_history.upsert_progress(
        track_key=key,
        title=key,
        author=author,
        source="youtube",
        position_ms=0,
        duration_ms=180_000,
        listen_increment=times,
        db_path=db,
    )


def test_finished_listens_go_to_log_and_rhythm(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    _finish(db, "yt:a", "A", times=2)
    sync_history.upsert_progress(
        track_key="yt:b",
        title="b",
        author="B",
        source="youtube",
        position_ms=0,
        duration_ms=1,
        db_path=db,
    )
    # Мало записей в журнале — ритм по last_played_at, только дослушанные.
    rhythm = sync_history.fetch_listening_rhythm(db)
    assert not rhythm.exact
    assert rhythm.total == 1 and sum(rhythm.weekdays) == 1

    for _ in range(25):
        _finish(db, "yt:a", "A", times=2)
    rhythm = sync_history.fetch_listening_rhythm(db)
    assert rhythm.exact
    assert rhythm.total == 52


def test_top_artists_group_by_primary_artist(tmp_path: Path) -> None:
    db = tmp_path / "h.db"
    _finish(db, "yt:n1", "Narvent", times=5)
    _finish(db, "yt:n2", "Narvent, VØJ", times=3)
    _finish(db, "yt:r1", "Radiohead", times=6)
    artists = sync_history.fetch_top_artists(5, db)
    assert [(a.author, a.listens, a.tracks) for a in artists] == [
        ("Narvent", 8, 2),
        ("Radiohead", 6, 1),
    ]
    assert artists[0].top_track_key == "yt:n1"
    assert sync_history.fetch_listening_summary(db).top_artist == "Narvent"


# --- карточка ---------------------------------------------------------------


def _click(widget, pos: QPointF) -> None:
    for kind in (
        QMouseEvent.Type.MouseButtonPress,
        QMouseEvent.Type.MouseButtonRelease,
    ):
        event = QMouseEvent(
            kind,
            pos,
            widget.mapToGlobal(pos),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        if kind == QMouseEvent.Type.MouseButtonPress:
            widget.mousePressEvent(event)
        else:
            widget.mouseReleaseEvent(event)


def test_art_card_play_button_plays_rest_opens(qapp) -> None:
    from quantis.ui.views.widgets.art_card import ArtCard

    card = ArtCard("item", title="Микс", covers=lambda size: [None])
    card.apply_cell(180, 180 + ArtCard.ROW_EXTRA)
    played: list[object] = []
    opened: list[object] = []
    card.play_requested.connect(played.append)
    card.activated.connect(opened.append)

    _click(card, card.play_rect().center())
    _click(card, QPointF(20, 20))

    assert played == ["item"]
    assert opened == ["item"]
