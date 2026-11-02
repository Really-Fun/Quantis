"""Тесты форматов скачивания YouTube."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from quantis.models import YoutubeTrack
from quantis.models.track import Track
from quantis.providers import PathProvider
from quantis.services.async_downloader import (
    _AUDIO_FORMAT,
    _VIDEO_FORMAT,
    AsyncDownloader,
    AsyncSoundCloudDownloader,
    AsyncYandexDownloader,
    AsyncYoutubeDownloader,
    DownloadedAudio,
    meta_from_yandex,
    meta_from_ydl,
)
from quantis.services.track_tags import TrackMeta


def _meta() -> TrackMeta:
    return TrackMeta(source="youtube", track_id="vid", title="T", artist="A")


def test_audio_format_prefers_m4a_mp3() -> None:
    assert "m4a" in _AUDIO_FORMAT
    assert "mp3" in _AUDIO_FORMAT
    assert "mp4" not in _AUDIO_FORMAT


def test_video_format_is_mp4() -> None:
    assert "mp4" in _VIDEO_FORMAT
    assert "height<=360" in _VIDEO_FORMAT
    assert "height<=720" not in _VIDEO_FORMAT


def test_video_opts_skip_long_mixes() -> None:
    downloader = AsyncYoutubeDownloader()
    opts = downloader._ydl_opts("/tmp/%(ext)s", video=True)
    assert opts["match_filter"] is not None
    assert opts["match_filter"]({"duration": 3600}) is not None
    assert opts["match_filter"]({"duration": 120}) is None
    audio_opts = downloader._ydl_opts("/tmp/%(ext)s", video=False)
    assert "match_filter" not in audio_opts


@pytest.mark.asyncio
async def test_download_track_skips_video_when_wallpaper_off() -> None:
    downloader = AsyncYoutubeDownloader()

    with (
        patch.object(
            downloader,
            "_download_audio",
            return_value=DownloadedAudio(Path("x.m4a"), _meta()),
        ) as audio_mock,
        patch.object(downloader, "_download_video_cache") as video_mock,
        patch.object(downloader, "_video_wallpaper_enabled", return_value=False),
    ):
        track = YoutubeTrack(track_id="vid", title="T", author="A")
        await downloader.download_track(track)

    audio_mock.assert_awaited_once()
    video_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_download_track_fetches_video_cache_when_wallpaper_on() -> None:
    downloader = AsyncYoutubeDownloader()

    with (
        patch.object(
            downloader,
            "_download_audio",
            return_value=DownloadedAudio(Path("x.m4a"), _meta()),
        ) as audio_mock,
        patch.object(downloader, "_download_video_cache") as video_mock,
        patch.object(downloader, "_video_wallpaper_enabled", return_value=True),
    ):
        track = YoutubeTrack(track_id="vid", title="T", author="A")
        await downloader.download_track(track)

    audio_mock.assert_awaited_once()
    video_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_cover_redownloads_truncated_file(tmp_path: Path) -> None:
    dest = tmp_path / "vid.jpg"
    dest.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 5000)
    downloader = AsyncDownloader()
    track = YoutubeTrack(track_id="vid", title="T", author="A")
    good = b"\xff\xd8\xff\xe0" + b"\x22" * 5000 + b"\xff\xd9"

    async def fake_download(_track) -> None:
        dest.write_bytes(good)

    with (
        patch.object(
            downloader._youtube_downloader.path_provider,
            "get_cover_path",
            return_value=str(dest),
        ),
        patch.object(
            downloader._yandex_downloader.path_provider,
            "get_cover_path",
            return_value=str(dest),
        ),
        patch.object(
            downloader, "download_cover", new=AsyncMock(side_effect=fake_download)
        ),
    ):
        assert await downloader.ensure_cover(track) is True

    assert dest.read_bytes() == good


def _ya_track(albums):
    return SimpleNamespace(albums=albums)


def test_meta_from_yandex_full() -> None:
    album = SimpleNamespace(
        title="Alb",
        year=2020,
        genre="pop",
        track_position=SimpleNamespace(index=5),
        artists=[SimpleNamespace(name="X"), SimpleNamespace(name="Y")],
    )
    track = Track(track_id=1, title="T", author="A", source="yandex")
    meta = meta_from_yandex(track, _ya_track([album]))
    assert meta.album == "Alb"
    assert meta.year == 2020
    assert meta.genre == "pop"
    assert meta.track_number == 5
    assert meta.album_artist == "X, Y"
    assert meta.title == "T" and meta.artist == "A"
    assert meta.source == "yandex" and meta.track_id == "1"
    assert meta.source_url == "https://music.yandex.ru/track/1"


def test_meta_from_yandex_no_albums() -> None:
    track = Track(track_id=1, title="T", author="A", source="yandex")
    for ya in (_ya_track([]), _ya_track(None)):
        meta = meta_from_yandex(track, ya)
        assert meta.album == "" and meta.year is None


def test_meta_from_yandex_none_fields() -> None:
    album = SimpleNamespace(
        title=None, year=None, genre=None, track_position=None, artists=None
    )
    track = Track(track_id=1, title="T", author="A", source="yandex")
    meta = meta_from_yandex(track, _ya_track([album]))
    assert meta.album == "" and meta.track_number is None
    assert meta.album_artist == "" and meta.genre == ""


def test_meta_from_ydl_youtube() -> None:
    track = YoutubeTrack(track_id="vid", title="T", author="A")
    meta = meta_from_ydl(track, {"album": "A", "release_year": 2019})
    assert meta.year == 2019 and meta.genre == "" and meta.album == "A"
    assert meta.source == "youtube"
    assert meta.source_url == "https://music.youtube.com/watch?v=vid"


def test_meta_from_ydl_soundcloud_upload_date() -> None:
    track = Track(track_id=123, title="T", author="A", source="soundcloud")
    meta = meta_from_ydl(track, {"genre": "House", "upload_date": "20180102"})
    assert meta.year == 2018 and meta.genre == "House"
    assert meta_from_ydl(track, {"upload_date": "bad"}).year is None
    assert meta_from_ydl(track, {}).year is None


@pytest.mark.asyncio
@pytest.mark.parametrize("production_like", [True, False])
async def test_youtube_download_returns_path_from_info(
    tmp_path: Path, monkeypatch, production_like: bool
) -> None:
    monkeypatch.setattr(
        PathProvider, "MUSIC_FOLDER", None if production_like else str(tmp_path)
    )
    downloader = AsyncYoutubeDownloader()
    audio = tmp_path / "vid_T_A.m4a"
    audio.write_bytes(b"x")
    info = {"requested_downloads": [{"filepath": str(audio)}], "album": "Al"}
    track = YoutubeTrack(track_id="vid", title="T", author="A")
    with patch.object(downloader, "sync_download", return_value=info):
        result = await downloader._download_audio(track)
    assert result is not None
    assert result.path == audio
    assert result.meta.album == "Al"
    assert track.extension == "m4a"


@pytest.mark.asyncio
async def test_youtube_download_bad_extension_returns_none(tmp_path: Path) -> None:
    downloader = AsyncYoutubeDownloader()
    info = {"requested_downloads": [{"filepath": str(tmp_path / "v.webm")}]}
    track = YoutubeTrack(track_id="vid", title="T", author="A")
    with patch.object(downloader, "sync_download", return_value=info):
        assert await downloader._download_audio(track) is None


@pytest.mark.asyncio
async def test_youtube_download_failure_returns_none() -> None:
    downloader = AsyncYoutubeDownloader()
    track = YoutubeTrack(track_id="vid", title="T", author="A")
    with patch.object(downloader, "sync_download", side_effect=RuntimeError("x")):
        assert await downloader._download_audio(track) is None
        assert await downloader.download_track(track) is None
        assert await downloader.fetch_meta(track) is None


@pytest.mark.asyncio
async def test_youtube_fetch_meta_falls_back() -> None:
    downloader = AsyncYoutubeDownloader()
    track = YoutubeTrack(track_id="vid", title="T", author="A")
    calls = []

    def fake(opts, _id):
        calls.append(opts)
        if len(calls) == 1:
            raise RuntimeError("x")
        return {"genre": "Rock"}

    with patch.object(downloader, "sync_extract", side_effect=fake):
        meta = await downloader.fetch_meta(track)
    assert meta is not None and meta.genre == "Rock"
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("production_like", [True, False])
async def test_soundcloud_download_returns_path(
    tmp_path: Path, monkeypatch, production_like: bool
) -> None:
    monkeypatch.setattr(
        PathProvider, "MUSIC_FOLDER", None if production_like else str(tmp_path)
    )
    monkeypatch.setattr(PathProvider, "ensure_storage_dirs", staticmethod(lambda: None))
    downloader = AsyncSoundCloudDownloader()
    audio = tmp_path / "sc1_T_A.mp3"
    audio.write_bytes(b"x")
    info = {"requested_downloads": [{"filepath": str(audio)}], "genre": "House"}
    from quantis.models.track import SoundCloudTrack

    track = SoundCloudTrack(track_id="1", title="T", author="A")
    with patch.object(downloader, "sync_download", return_value=info):
        result = await downloader.download_track(track)
    assert result is not None and result.path == audio
    assert result.meta.genre == "House" and track.extension == "mp3"


@pytest.mark.asyncio
async def test_soundcloud_failure_returns_none() -> None:
    downloader = AsyncSoundCloudDownloader()
    track = Track(track_id=1, title="T", author="A", source="soundcloud")
    with (
        patch.object(PathProvider, "ensure_storage_dirs"),
        patch.object(downloader, "sync_download", side_effect=RuntimeError("x")),
    ):
        assert await downloader.download_track(track) is None


@pytest.mark.asyncio
async def test_yandex_download_returns_path_and_meta(tmp_path: Path) -> None:
    downloader = AsyncYandexDownloader()
    dest = tmp_path / "1_T_A.mp3"
    album = SimpleNamespace(
        title="Alb", year=2020, genre=None, track_position=None, artists=[]
    )

    async def fake_dl(path, bitrate_in_kbps):
        Path(path).write_bytes(b"x")  # noqa: ASYNC240

    ya = SimpleNamespace(albums=[album], download_async=fake_dl)
    client = SimpleNamespace(token="t", tracks=AsyncMock(return_value=[ya]))
    downloader._client, downloader._client_ready = client, True
    track = Track(track_id=1, title="T", author="A", source="yandex")
    with (
        patch.object(PathProvider, "ensure_storage_dirs"),
        patch.object(
            downloader.path_provider, "get_track_path", return_value=str(dest)
        ),
    ):
        result = await downloader.download_track(track)
        meta = await downloader.fetch_meta(track)
    assert result is not None and result.path == dest
    assert result.meta.album == "Alb" and meta is not None and meta.year == 2020
    client.tracks = AsyncMock(side_effect=RuntimeError("x"))
    assert await downloader.fetch_meta(track) is None
