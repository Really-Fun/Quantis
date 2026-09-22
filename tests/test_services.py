"""Unit-тесты слоя services (без сети)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from quantis.models import SoundCloudTrack, YandexTrack, YoutubeTrack
from quantis.services.async_finder import AsyncFinder, AsyncYandexFinder
from quantis.services.async_streamer import AsyncStreamer
from quantis.services.music_service import MusicService


@pytest.mark.asyncio
async def test_streamer_routes_youtube_track() -> None:
    streamer = AsyncStreamer()
    track = YoutubeTrack(track_id="abc123", title="Test", author="Artist")

    with patch.object(
        streamer._youtube,
        "get_stream_url",
        new_callable=AsyncMock,
        return_value="http://yt",
    ) as youtube_mock:
        url = await streamer.get_stream_url(track)

    assert url == "http://yt"
    youtube_mock.assert_awaited_once_with(track)
    streamer.shutdown()


@pytest.mark.asyncio
async def test_streamer_routes_soundcloud_track() -> None:
    streamer = AsyncStreamer()
    track = SoundCloudTrack(track_id="123", title="Test", author="Artist")

    with patch.object(
        streamer._soundcloud,
        "get_stream_url",
        new_callable=AsyncMock,
        return_value="http://sc",
    ) as sc_mock:
        url = await streamer.get_stream_url(track)

    assert url == "http://sc"
    sc_mock.assert_awaited_once_with(track)
    streamer.shutdown()


@pytest.mark.asyncio
async def test_streamer_cache_key_includes_source() -> None:
    streamer = AsyncStreamer()
    yandex = YandexTrack(track_id="123", title="T", author="A")
    youtube = YoutubeTrack(track_id="123", title="T", author="A")

    with patch.object(
        streamer._yandex,
        "get_stream_url",
        new_callable=AsyncMock,
        return_value="yandex-url",
    ):
        first = await streamer.get_stream_url(yandex)
        second = await streamer.get_stream_url(yandex)

    assert first == second == "yandex-url"

    with patch.object(
        streamer._youtube,
        "get_stream_url",
        new_callable=AsyncMock,
        return_value="youtube-url",
    ) as youtube_mock:
        url = await streamer.get_stream_url(youtube)

    assert url == "youtube-url"
    youtube_mock.assert_awaited_once()
    streamer.shutdown()


@pytest.mark.asyncio
async def test_streamer_unknown_source_raises() -> None:
    streamer = AsyncStreamer()
    track = YandexTrack(track_id="1", title="T", author="A")
    track.source = "spotify"

    with pytest.raises(ValueError, match="Неизвестный источник"):
        await streamer.get_stream_url(track)

    streamer.shutdown()


@pytest.mark.asyncio
async def test_finder_skips_yandex_for_youtube_id() -> None:
    finder = AsyncFinder()
    youtube_track = YoutubeTrack(track_id="dQw4w9WgXcQ", title="Never", author="Rick")

    with (
        patch.object(
            finder._yandex_finder,
            "get_track",
            new_callable=AsyncMock,
            return_value=None,
        ) as yandex_mock,
        patch.object(
            finder._youtube_finder,
            "get_track",
            new_callable=AsyncMock,
            return_value=youtube_track,
        ) as youtube_mock,
    ):
        result = await finder.get_track("dQw4w9WgXcQ")

    assert result is youtube_track
    yandex_mock.assert_not_awaited()
    youtube_mock.assert_awaited_once_with("dQw4w9WgXcQ")
    finder.shutdown()


@pytest.mark.asyncio
async def test_finder_tries_yandex_for_numeric_id() -> None:
    finder = AsyncFinder()
    yandex_track = YandexTrack(track_id="42", title="Track", author="Artist")

    with (
        patch.object(
            finder._yandex_finder,
            "get_track",
            new_callable=AsyncMock,
            return_value=yandex_track,
        ) as yandex_mock,
        patch.object(
            finder._youtube_finder, "get_track", new_callable=AsyncMock
        ) as youtube_mock,
    ):
        result = await finder.get_track("42")

    assert result is yandex_track
    yandex_mock.assert_awaited_once_with("42")
    youtube_mock.assert_not_awaited()
    finder.shutdown()


@pytest.mark.asyncio
async def test_yandex_finder_get_track_rejects_non_numeric_id() -> None:
    finder = AsyncYandexFinder()
    result = await finder.get_track("not-a-number")
    assert result is None


def test_music_service_wires_recommendation_with_youtube_finder() -> None:
    finder = AsyncFinder()
    service = MusicService(finder=finder)

    assert service.recommendation._finder is finder.youtube
    service.shutdown()


def test_music_service_shutdown_does_not_raise() -> None:
    service = MusicService()
    service.shutdown()
