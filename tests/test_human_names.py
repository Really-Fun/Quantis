"""Человеческие имена файлов: «Исполнитель - Название.ext»."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from quantis.models import (
    YandexTrack,  # noqa: F401  (порядок импорта: цикл soundcloud <-> path_provider)
)
from quantis.providers.path_provider import PathProvider
from quantis.services.track_tags import TrackMeta, write_tags

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PathProvider:
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(tmp_path))
    return PathProvider()


def test_basic_name(provider, tmp_path):
    path = provider.human_track_path("Artist", "Song", "mp3")
    assert path == tmp_path / "Artist - Song.mp3"


def test_invalid_chars(provider):
    path = provider.human_track_path("AC/DC", 'Who? "Me"', "mp3")
    assert path.name == "AC_DC - Who_ _Me_.mp3"


def test_empty_parts(provider):
    assert provider.human_track_path("", "  ", "mp3").name == "unknown - unknown.mp3"


def _base(path):
    return path.stem.split(".", 1)[0].rstrip(" .").upper()


def test_reserved_names(provider):
    from quantis.providers.path_provider import _RESERVED_NAMES

    for artist in ("con.foo", "aux.txt", "aux. x", "LPT1.a", "nul.", "com9.x.y"):
        path = provider.human_track_path(artist, "bar", "mp3")
        assert _base(path) not in _RESERVED_NAMES, path.name
    assert provider.human_track_path("con.foo", "bar", "mp3").name == (
        "con_.foo - bar.mp3"
    )
    assert provider.human_track_path("NUL", "x", "mp3").name == "NUL - x.mp3"
    assert provider.human_track_path("Console", "x", "mp3").name == "Console - x.mp3"


def test_cyrillic_byte_cap(provider):
    path = provider.human_track_path("Я" * 300, "ж" * 300, "mp3")
    assert len(path.stem) <= 150
    assert len(path.stem.encode("utf-8")) <= 200


def test_emoji_byte_cap(provider):
    path = provider.human_track_path("A", "🔥" * 100, "mp3")
    assert len(path.stem.encode("utf-8")) <= 200
    assert path.stem.encode("utf-8").decode("utf-8") == path.stem
    assert path.stem.startswith("A - 🔥")


def test_byte_cap_with_collision_suffix(provider, tmp_path):
    first = provider.human_track_path("Я" * 300, "ж" * 300, "mp3")
    first.write_bytes(b"x")
    second = provider.human_track_path("Я" * 300, "ж" * 300, "mp3")
    assert second != first and second.stem.endswith(" (2)")
    assert len(second.stem.encode("utf-8")) <= 200
    assert len(second.stem) <= 150


def test_truncation_leaves_no_trailing_space_or_dot(provider):
    title = "a" * 140 + " . " + "b" * 50
    path = provider.human_track_path("Artist", title, "mp3")
    assert path.stem == path.stem.rstrip(" .")
    assert len(path.stem) <= 150
    narrow = provider.human_track_path("Artist", "x" * 130 + ". y", "mp3")
    assert narrow.stem == narrow.stem.rstrip(" .")


def test_case_only_collision_does_not_overwrite(provider, tmp_path):
    existing = tmp_path / "Artist - Song.mp3"
    existing.write_bytes(b"x")
    path = provider.human_track_path("artist", "song", "mp3")
    assert path != existing
    if (tmp_path / "ARTIST - SONG.MP3").exists():  # регистронезависимая ФС
        assert path.name == "artist - song (2).mp3"


def test_trailing_dot_and_emoji(provider):
    assert provider.human_track_path("A", "Song.", "mp3").name == "A - Song.mp3"
    assert provider.human_track_path("A", "🔥", "mp3").name == "A - 🔥.mp3"


def test_long_name_capped(provider):
    path = provider.human_track_path("a" * 300, "Song", "mp3")
    assert len(path.stem) <= 150
    assert path.stem.endswith(" - S")
    long_title = provider.human_track_path("Artist", "t" * 300, "mp3")
    assert len(long_title.stem) == 150
    assert long_title.stem.startswith("Artist - ttt")


def test_collision_with_foreign_file(provider, tmp_path):
    (tmp_path / "Artist - Song.mp3").write_bytes(b"x")
    assert provider.human_track_path("Artist", "Song", "mp3").name == (
        "Artist - Song (2).mp3"
    )
    (tmp_path / "Artist - Song (2).mp3").write_bytes(b"x")
    assert provider.human_track_path("Artist", "Song", "mp3").name == (
        "Artist - Song (3).mp3"
    )


def test_collision_suffix_fits_cap(provider, tmp_path):
    first = provider.human_track_path("a" * 300, "b" * 300, "mp3")
    first.write_bytes(b"x")
    second = provider.human_track_path("a" * 300, "b" * 300, "mp3")
    assert second != first
    assert second.stem.endswith(" (2)")
    assert len(second.stem) <= 150


def test_same_owner_reuses_path(provider, tmp_path):
    target = tmp_path / "Artist - Song.mp3"
    shutil.copy(FIXTURES / "silence.mp3", target)
    write_tags(
        target,
        TrackMeta(source="youtube", track_id="x", title="Song", artist="Artist"),
        cover=None,
    )
    assert (
        provider.human_track_path("Artist", "Song", "mp3", owner=("youtube", "x"))
        == target
    )
    other = provider.human_track_path("Artist", "Song", "mp3", owner=("youtube", "y"))
    assert other.name == "Artist - Song (2).mp3"
    assert (
        provider.human_track_path("Artist", "Song", "mp3").name
        == "Artist - Song (2).mp3"
    )
