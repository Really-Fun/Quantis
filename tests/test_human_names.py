"""Человеческие имена файлов: «Исполнитель - Название.ext»."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from quantis.models import YandexTrack  # noqa: F401  (порядок импорта: цикл soundcloud <-> path_provider)
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


def test_reserved_names(provider):
    assert provider.human_track_path("", "CON", "mp3").stem.upper() != "CON"
    assert provider.human_track_path("nul", "x", "mp3").name == "nul - x.mp3"
    assert PathProvider._avoid_reserved("CON") == "CON_"
    assert PathProvider._avoid_reserved("lpt3") == "lpt3_"
    assert PathProvider._avoid_reserved("Console") == "Console"


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
    write_tags(target, TrackMeta(source="youtube", track_id="x", title="Song", artist="Artist"), cover=None)
    assert provider.human_track_path("Artist", "Song", "mp3", owner=("youtube", "x")) == target
    other = provider.human_track_path("Artist", "Song", "mp3", owner=("youtube", "y"))
    assert other.name == "Artist - Song (2).mp3"
    assert provider.human_track_path("Artist", "Song", "mp3").name == "Artist - Song (2).mp3"
