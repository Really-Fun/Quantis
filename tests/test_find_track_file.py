"""Скачанный трек находится, даже если имя файла разошлось с title/author."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantis.models import YandexTrack, YoutubeTrack
from quantis.providers.path_provider import PathProvider


@pytest.fixture
def provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> PathProvider:
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(tmp_path))
    return PathProvider()


def test_youtube_author_stats_stripped_but_file_found(
    provider: PathProvider, tmp_path: Path
) -> None:
    # Файл назван ещё со статистикой, а YoutubeTrack её из автора вычищает.
    name = "1cnR-iFl3D0_Real For Me_Nikkie, Narvent, Отметок _Нравится__ 24 тыс.m4a"
    (tmp_path / name).write_bytes(b"audio")
    track = YoutubeTrack(
        track_id="1cnR-iFl3D0",
        title="Real For Me",
        author="Nikkie, Narvent, Отметок _Нравится__ 24 тыс",
        downloaded=True,
        extension="m4a",
    )

    assert not Path(provider.get_track_path(track)).is_file()
    assert provider.find_track_file(track) == str(tmp_path / name)


def test_exact_path_preferred(provider: PathProvider, tmp_path: Path) -> None:
    track = YandexTrack(track_id="42", title="Song", author="Artist")
    exact = Path(provider.get_track_path(track))
    exact.write_bytes(b"audio")
    (tmp_path / "42_Old title_Artist.mp3").write_bytes(b"audio")

    assert provider.find_track_file(track) == str(exact)


def test_ignores_empty_foreign_and_non_audio(
    provider: PathProvider, tmp_path: Path
) -> None:
    (tmp_path / "42_Song_Artist.mp3").write_bytes(b"")
    (tmp_path / "42_Song_Artist.webm.part").write_bytes(b"x")
    (tmp_path / "420_Song_Artist.mp3").write_bytes(b"audio")
    track = YandexTrack(track_id="42", title="Song", author="Artist")

    assert provider.find_track_file(track) is None
