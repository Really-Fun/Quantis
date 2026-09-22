"""Unit-тесты SoundCloud: URL, файлы, выбор формата, маршрутизация."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from quantis.models import SoundCloudTrack
from quantis.providers.path_provider import PathProvider
from quantis.services.async_downloader import AsyncDownloader
from quantis.services.soundcloud import (
    parse_storage_id,
    storage_id,
    track_from_ydl,
    watch_url,
)
from quantis.services.soundcloud_streamer import AsyncSoundCloudStreamer


def test_watch_url_from_numeric_id() -> None:
    assert watch_url("12345") == "https://api.soundcloud.com/tracks/12345"


def test_watch_url_from_permalink() -> None:
    assert watch_url("artist/track") == "https://soundcloud.com/artist/track"


def test_watch_url_keeps_absolute() -> None:
    url = "https://on.soundcloud.com/AbCd"
    assert watch_url(url) == url


def test_watch_url_rejects_foreign_host() -> None:
    with pytest.raises(ValueError, match="SoundCloud"):
        watch_url("https://evil.example/track")


def test_storage_id_prefixes_numeric() -> None:
    assert storage_id("12345") == "sc12345"
    assert storage_id("sc12345") == "sc12345"
    assert parse_storage_id("sc12345") == "12345"
    assert parse_storage_id("dQw4w9WgXcQ") is None


def test_path_provider_soundcloud_does_not_collide_with_yandex() -> None:
    provider = PathProvider()
    sc = SoundCloudTrack(track_id="42", title="T", author="A")
    assert provider.storage_id(sc) == "sc42"
    assert provider.get_cover_path(sc).endswith("sc42.jpg")


def test_path_provider_sanitizes_templates_and_uses_track_extension() -> None:
    from quantis.models import YoutubeTrack

    provider = PathProvider()
    track = YoutubeTrack(
        track_id="dQw4w9WgXcQ",
        title="100%% %(ext)s ../x",
        author="A",
    )
    path = provider.get_track_path(track)
    name = Path(path).name
    assert name.startswith("dQw4w9WgXcQ_")
    assert name.endswith(".m4a")
    assert "%" not in name
    assert ".." not in name
    templated = provider.get_track_path(track, extension="%(ext)s")
    assert templated.endswith(".%(ext)s")


def test_track_from_ydl_reads_thumbnail() -> None:
    track = track_from_ydl(
        {
            "id": "99",
            "title": "Song",
            "uploader": "Artist",
            "thumbnails": [
                {"url": "https://i1.sndcdn.com/small.jpg"},
                {"url": "https://i1.sndcdn.com/large.jpg"},
            ],
        }
    )
    assert track is not None
    assert track.track_id == "99"
    assert track.author == "Artist"
    assert track.thumbnail_url.endswith("large.jpg")


def test_picks_progressive_mp3_over_hls() -> None:
    info = {
        "formats": [
            {
                "url": "https://cf-hls-media.sndcdn.com/playlist.m3u8",
                "protocol": "m3u8_native",
                "ext": "mp3",
                "abr": 128,
                "format_id": "hls_mp3_0_0",
            },
            {
                "url": "https://cf-media.sndcdn.com/track.mp3",
                "protocol": "https",
                "ext": "mp3",
                "abr": 128,
                "format_id": "http_mp3_0_0",
            },
        ]
    }
    assert (
        AsyncSoundCloudStreamer._pick_stream_url(info)
        == "https://cf-media.sndcdn.com/track.mp3"
    )


def test_skips_preview_when_full_stream_exists() -> None:
    info = {
        "url": "https://cf-preview-media.sndcdn.com/preview/0/30/x.mp3",
        "protocol": "http",
        "ext": "mp3",
        "format_id": "http_mp3_1_0_preview",
        "formats": [
            {
                "url": "https://cf-preview-media.sndcdn.com/preview/0/30/x.mp3",
                "protocol": "http",
                "ext": "mp3",
                "abr": 128,
                "format_id": "http_mp3_1_0_preview",
            },
            {
                "url": "https://cf-media.sndcdn.com/full.mp3",
                "protocol": "http",
                "ext": "mp3",
                "abr": 128,
                "format_id": "http_mp3_0_0",
            },
        ],
    }
    assert AsyncSoundCloudStreamer._pick_stream_url(info) == (
        "https://cf-media.sndcdn.com/full.mp3"
    )


@pytest.mark.asyncio
async def test_downloader_routes_soundcloud() -> None:
    downloader = AsyncDownloader()
    track = SoundCloudTrack(track_id="1", title="T", author="A")

    with patch.object(
        downloader._soundcloud_downloader,
        "download_track",
        new_callable=AsyncMock,
    ) as track_mock:
        await downloader.download_track(track)

    track_mock.assert_awaited_once_with(track)

    with patch.object(
        downloader._soundcloud_downloader,
        "download_cover",
        new_callable=AsyncMock,
    ) as cover_mock:
        await downloader.download_cover(track)

    cover_mock.assert_awaited_once_with(track)
