"""Временные обложки, перенос в библиотеку и совместимость со старыми файлами."""

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from quantis.models import DownloadPlaylist, YandexTrack
from quantis.providers import PathProvider
from quantis.services import cover_storage
from quantis.services.async_downloader import AsyncDownloader
from quantis.services.user_playlists import UserPlaylistsService

JPEG = b"\xff\xd8" + b"x" * 4096 + b"\xff\xd9"


@pytest.fixture
def paths(tmp_path, monkeypatch):
    for key, folder in (
        ("COVERS_FOLDER", "covers"),
        ("MUSIC_FOLDER", "music"),
        ("PLAYLISTS_FOLDER", "playlists"),
    ):
        monkeypatch.setattr(PathProvider, key, str(tmp_path / folder))
    PathProvider.ensure_storage_dirs()
    return PathProvider()


def test_cache_evicts_oldest_search_art_only(paths, tmp_path, monkeypatch):
    monkeypatch.setattr(cover_storage, "_CACHE_BYTES", 2 * len(JPEG))
    tracks = [YandexTrack(i, "Song", "Artist") for i in range(5)]
    legacy = paths.permanent_cover_path(tracks[0])
    legacy.write_bytes(JPEG)
    tracks[1].downloaded = True
    for track in tracks[1:]:
        assert cover_storage.store_cover(track, JPEG)
        if track.track_id == 2:
            os.utime(paths.cached_cover_path(track), (1, 1))
    assert Path(paths.get_cover_path(tracks[0])) == legacy
    assert paths.permanent_cover_path(tracks[1]).read_bytes() == JPEG
    assert not paths.cached_cover_path(tracks[2]).exists()
    assert sorted((tmp_path / "cache" / "covers").glob("*.jpg")) == [
        paths.cached_cover_path(track) for track in tracks[3:]
    ]


@pytest.mark.asyncio
async def test_playlist_promotes_existing_and_retains_future_art(paths):
    playlist = UserPlaylistsService()
    await playlist.create("Mix")
    cached = YandexTrack(1, "One", "Artist")
    pending = YandexTrack(2, "Two", "Artist")
    assert cover_storage.store_cover(cached, JPEG)
    await playlist.add_track("Mix", cached)
    assert not paths.cached_cover_path(cached).exists()
    await playlist.add_track("Mix", pending)
    assert cover_storage.store_cover(pending, JPEG)
    DownloadPlaylist(tracks=[cached]).delete_track(cached)
    for track in (cached, pending):
        assert paths.permanent_cover_path(track).read_bytes() == JPEG


@pytest.mark.asyncio
async def test_download_promotes_search_cover_without_refetch(paths):
    track = YandexTrack(7, "Song", "Artist")
    dl = AsyncDownloader()
    ya = dl._yandex_downloader
    ya._client = SimpleNamespace(
        tracks=AsyncMock(
            return_value=[
                SimpleNamespace(download_cover_bytes_async=AsyncMock(return_value=JPEG))
            ]
        )
    )
    ya._client_ready = True
    assert await dl.ensure_cover(track)
    assert paths.cached_cover_path(track).read_bytes() == JPEG
    dl._index = SimpleNamespace(
        wait_ready=AsyncMock(), path_for=lambda *_: Path("existing.mp3")
    )
    assert await dl.download_full(track)
    ya._client.tracks.assert_awaited_once()
    assert paths.permanent_cover_path(track).read_bytes() == JPEG
    assert not paths.cached_cover_path(track).exists()
