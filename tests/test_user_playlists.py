"""Тесты пользовательских плейлистов (JSON)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quantis.models import YandexTrack
from quantis.utils import playlist_helper as helper


@pytest.fixture()
def playlists_dir(tmp_path: Path) -> str:
    path = tmp_path / "playlists"
    path.mkdir()
    return str(path)


def test_create_and_add_track(playlists_dir: str) -> None:
    helper.create_user_playlist_file("Мой микс", playlists_dir)
    names = helper.list_user_playlist_names(playlists_dir)
    assert names == ["Мой микс"]

    added = helper.add_track_to_user_playlist(
        "Мой микс",
        42,
        "Song",
        "Artist",
        playlists_dir,
        source="yandex",
    )
    assert added is True
    again = helper.add_track_to_user_playlist(
        "Мой микс",
        42,
        "Song",
        "Artist",
        playlists_dir,
        source="yandex",
    )
    assert again is False

    from quantis.models.playlist import UserPlaylist

    path = helper.get_user_playlist_path_by_name("Мой микс", playlists_dir)
    playlist = UserPlaylist.get_playlist_from_path(str(path))
    assert playlist is not None
    assert len(playlist) == 1
    assert playlist.tracks.values[0].title == "Song"

    removed = helper.remove_track_from_user_playlist("Мой микс", 42, playlists_dir)
    assert removed is True
    missing = helper.remove_track_from_user_playlist("Мой микс", 42, playlists_dir)
    assert missing is False
    playlist = UserPlaylist.get_playlist_from_path(str(path))
    assert playlist is not None
    assert len(playlist) == 0


@pytest.mark.asyncio
async def test_user_playlists_service(tmp_path: Path, monkeypatch) -> None:
    from quantis.providers.path_provider import PathProvider
    from quantis.services.user_playlists import UserPlaylistsService

    playlists = tmp_path / "playlists"
    playlists.mkdir()
    monkeypatch.setattr(PathProvider, "PLAYLISTS_FOLDER", str(playlists) + "/")
    # Reset singleton
    UserPlaylistsService._instance = None
    service = UserPlaylistsService()
    await service.create("Test")
    track = YandexTrack(track_id=1, title="T", author="A")
    assert await service.add_track("Test", track) is True
    loaded = await service.load_all(include_empty=True)
    assert any(p.name == "Test" for p in loaded)
    assert await service.remove_track("Test", track) is True
    loaded = await service.load_all(include_empty=True)
    match = next(p for p in loaded if p.name == "Test")
    assert len(match) == 0
    UserPlaylistsService._instance = None


def test_download_playlist_delete_track_removes_files(
    tmp_path: Path, monkeypatch
) -> None:
    from quantis.models.playlist import DownloadPlaylist
    from quantis.providers.path_provider import PathProvider

    music = tmp_path / "music"
    covers = tmp_path / "covers"
    music.mkdir()
    covers.mkdir()
    monkeypatch.setattr(PathProvider, "MUSIC_FOLDER", str(music))
    monkeypatch.setattr(PathProvider, "COVERS_FOLDER", str(covers))

    track = YandexTrack(track_id=99, title="Song", author="Artist")
    provider = PathProvider()
    audio = Path(provider.get_track_path(track))
    cover = Path(provider.get_cover_path(track))
    audio.write_bytes(b"id3")
    cover.write_bytes(b"jpg")

    playlist = DownloadPlaylist(tracks=[track])
    assert playlist.delete_track(track) is True
    assert not audio.exists()
    assert not cover.exists()
    assert len(playlist) == 0
    assert track.downloaded is False
