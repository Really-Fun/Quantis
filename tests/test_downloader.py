"""Тесты форматов скачивания YouTube."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from quantis.models import YoutubeTrack
from quantis.services.async_downloader import (
    _AUDIO_FORMAT,
    _VIDEO_FORMAT,
    AsyncDownloader,
    AsyncYoutubeDownloader,
)


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
        patch.object(downloader, "_download_audio", return_value=True) as audio_mock,
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
        patch.object(downloader, "_download_audio", return_value=True) as audio_mock,
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
