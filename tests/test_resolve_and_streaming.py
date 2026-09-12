"""Unit-тесты resolve_tracks и VLC routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from quantis.models import SoundCloudTrack, YandexTrack, YoutubeTrack
from quantis.services.async_finder import AsyncFinder
from quantis.services.async_streamer import (
    AsyncStreamer,
    is_hls_url,
    should_buffer_stream,
    should_proxy_stream,
)

_BACKEND = "quantis.services.async_streamer.resolve_media_backend"


def test_is_hls_url() -> None:
    assert is_hls_url("https://cf-hls-media.sndcdn.com/playlist.m3u8")
    assert is_hls_url("https://api.soundcloud.com/media/x/stream/hls")
    assert not is_hls_url("https://cf-media.sndcdn.com/track.mp3")
    assert not is_hls_url(None)


def test_should_buffer_stream_by_backend() -> None:
    yandex = YandexTrack(track_id="1", title="T", author="A")
    sc = SoundCloudTrack(track_id="2", title="T", author="A")
    youtube = YoutubeTrack(track_id="abc", title="T", author="A")
    hls = "https://cf-hls-media.sndcdn.com/playlist.m3u8"
    mp3 = "https://cf-media.sndcdn.com/track.mp3"

    assert not should_buffer_stream(yandex, backend="qt")
    assert not should_buffer_stream(yandex, backend="vlc")
    assert should_proxy_stream(yandex, backend="qt")
    assert not should_proxy_stream(yandex, backend="vlc")
    assert should_proxy_stream(sc, backend="qt", url=mp3)
    assert not should_proxy_stream(sc, backend="qt", url=hls)
    assert not should_proxy_stream(youtube, backend="qt")


@pytest.mark.asyncio
async def test_resolve_tracks_yandex_url() -> None:
    finder = AsyncFinder()
    track = YandexTrack(track_id="123", title="T", author="A")

    with patch.object(
        finder._yandex_finder, "get_track", new_callable=AsyncMock, return_value=track
    ) as yandex_mock:
        result = await finder.resolve_tracks(
            url="https://music.yandex.ru/album/1/track/123"
        )

    assert result == [track]
    yandex_mock.assert_awaited_once_with("123")
    finder.shutdown()


@pytest.mark.asyncio
async def test_resolve_tracks_youtube_url() -> None:
    finder = AsyncFinder()
    video_id = "dQw4w9WgXcQ"
    track = YoutubeTrack(track_id=video_id, title="T", author="A")

    with patch.object(
        finder._youtube_finder,
        "get_track_from_url",
        new_callable=AsyncMock,
        return_value=track,
    ) as yt_mock:
        result = await finder.resolve_tracks(
            url=f"https://www.youtube.com/watch?v={video_id}"
        )

    assert result == [track]
    yt_mock.assert_awaited_once()
    finder.shutdown()


@pytest.mark.asyncio
async def test_resolve_tracks_soundcloud_url() -> None:
    finder = AsyncFinder()
    track = SoundCloudTrack(track_id="123", title="T", author="A")
    url = "https://soundcloud.com/artist/track-name"

    with patch.object(
        finder._soundcloud_finder,
        "get_track_from_url",
        new_callable=AsyncMock,
        return_value=track,
    ) as sc_mock:
        result = await finder.resolve_tracks(url=url)

    assert result == [track]
    sc_mock.assert_awaited_once_with(url)
    finder.shutdown()


@pytest.mark.asyncio
async def test_resolve_tracks_by_id_and_source() -> None:
    finder = AsyncFinder()
    track = YoutubeTrack(track_id="abc", title="T", author="A")

    with patch.object(
        finder._youtube_finder, "get_track", new_callable=AsyncMock, return_value=track
    ) as yt_mock:
        result = await finder.resolve_tracks(track_id="abc", source="youtube")

    assert result == [track]
    yt_mock.assert_awaited_once_with("abc")
    finder.shutdown()


@pytest.mark.asyncio
async def test_resolve_tracks_by_id_soundcloud() -> None:
    finder = AsyncFinder()
    track = SoundCloudTrack(track_id="99", title="T", author="A")

    with patch.object(
        finder._soundcloud_finder,
        "get_track",
        new_callable=AsyncMock,
        return_value=track,
    ) as sc_mock:
        result = await finder.resolve_tracks(track_id="99", source="soundcloud")

    assert result == [track]
    sc_mock.assert_awaited_once_with("99")
    finder.shutdown()


@pytest.mark.asyncio
async def test_open_playback_yandex_uses_local_proxy() -> None:
    streamer = AsyncStreamer()
    track = YandexTrack(track_id="1", title="T", author="A")
    local = "http://127.0.0.1:9/yandex/1"

    with (
        patch.object(
            streamer._http_proxy,
            "mount",
            new_callable=AsyncMock,
            return_value=local,
        ) as proxy_mock,
        patch.object(
            streamer._stream_buffer,
            "open",
            new_callable=AsyncMock,
        ) as buffer_mock,
        patch.object(
            streamer,
            "get_stream_url",
            new_callable=AsyncMock,
            return_value="https://storage.mds.yandex.net/get-mp3/track.mp3",
        ) as url_mock,
    ):
        result = await streamer.open_playback(track)

    assert result == local
    proxy_mock.assert_awaited_once_with(
        track, "https://storage.mds.yandex.net/get-mp3/track.mp3"
    )
    buffer_mock.assert_not_awaited()
    url_mock.assert_awaited_once_with(track)
    streamer.shutdown()


@pytest.mark.asyncio
async def test_open_playback_youtube_uses_direct_url() -> None:
    streamer = AsyncStreamer()
    track = YoutubeTrack(track_id="abc123", title="T", author="A")

    with (
        patch.object(
            streamer._stream_buffer,
            "open",
            new_callable=AsyncMock,
        ) as buffer_mock,
        patch.object(
            streamer,
            "get_stream_url",
            new_callable=AsyncMock,
            return_value="https://googlevideo.com/videoplayback",
        ) as url_mock,
    ):
        result = await streamer.open_playback(track)

    assert result == "https://googlevideo.com/videoplayback"
    url_mock.assert_awaited_once_with(track)
    buffer_mock.assert_not_awaited()
    streamer.shutdown()


@pytest.mark.asyncio
async def test_open_playback_vlc_yandex_uses_direct_url() -> None:
    streamer = AsyncStreamer()
    track = YandexTrack(track_id="1", title="T", author="A")
    direct = "https://storage.mds.yandex.net/get-mp3/track.mp3"

    with (
        patch(_BACKEND, return_value="vlc"),
        patch.object(
            streamer._stream_buffer,
            "open",
            new_callable=AsyncMock,
        ) as buffer_mock,
        patch.object(
            streamer,
            "get_stream_url",
            new_callable=AsyncMock,
            return_value=direct,
        ) as url_mock,
    ):
        result = await streamer.open_playback(track)

    assert result == direct
    url_mock.assert_awaited_once_with(track)
    buffer_mock.assert_not_awaited()
    streamer.shutdown()


@pytest.mark.asyncio
async def test_open_playback_soundcloud_uses_direct_url() -> None:
    streamer = AsyncStreamer()
    track = SoundCloudTrack(track_id="123", title="T", author="A")
    direct = "https://cf-media.sndcdn.com/track.mp3"

    with (
        patch(_BACKEND, return_value="vlc"),
        patch.object(
            streamer._stream_buffer,
            "open",
            new_callable=AsyncMock,
        ) as buffer_mock,
        patch.object(
            streamer,
            "get_stream_url",
            new_callable=AsyncMock,
            return_value=direct,
        ) as url_mock,
    ):
        result = await streamer.open_playback(track)

    assert result == direct
    url_mock.assert_awaited_once_with(track)
    buffer_mock.assert_not_awaited()
    streamer.shutdown()


@pytest.mark.asyncio
async def test_open_playback_qt_yandex_uses_proxy() -> None:
    streamer = AsyncStreamer()
    track = YandexTrack(track_id="1", title="T", author="A")
    local = "http://127.0.0.1:9/yandex/1"

    with (
        patch(_BACKEND, return_value="qt"),
        patch.object(
            streamer._http_proxy,
            "mount",
            new_callable=AsyncMock,
            return_value=local,
        ) as proxy_mock,
        patch.object(
            streamer._stream_buffer,
            "open",
            new_callable=AsyncMock,
        ) as buffer_mock,
        patch.object(
            streamer,
            "get_stream_url",
            new_callable=AsyncMock,
            return_value="https://storage.mds.yandex.net/get-mp3/track.mp3",
        ) as url_mock,
    ):
        result = await streamer.open_playback(track)

    assert result == local
    proxy_mock.assert_awaited_once()
    buffer_mock.assert_not_awaited()
    url_mock.assert_awaited_once_with(track)
    streamer.shutdown()


@pytest.mark.asyncio
async def test_open_playback_qt_soundcloud_uses_proxy() -> None:
    streamer = AsyncStreamer()
    track = SoundCloudTrack(track_id="123", title="T", author="A")
    local = "http://127.0.0.1:9/soundcloud/123"

    with (
        patch(_BACKEND, return_value="qt"),
        patch.object(
            streamer._http_proxy,
            "mount",
            new_callable=AsyncMock,
            return_value=local,
        ) as proxy_mock,
        patch.object(
            streamer._stream_buffer,
            "open",
            new_callable=AsyncMock,
        ) as buffer_mock,
        patch.object(
            streamer,
            "get_stream_url",
            new_callable=AsyncMock,
            return_value="https://cf-media.sndcdn.com/track.mp3",
        ) as url_mock,
    ):
        result = await streamer.open_playback(track)

    assert result == local
    proxy_mock.assert_awaited_once()
    buffer_mock.assert_not_awaited()
    url_mock.assert_awaited_once_with(track)
    streamer.shutdown()


@pytest.mark.asyncio
async def test_open_playback_qt_soundcloud_hls_uses_direct_url() -> None:
    streamer = AsyncStreamer()
    track = SoundCloudTrack(track_id="123", title="T", author="A")
    hls = "https://cf-hls-media.sndcdn.com/playlist.m3u8"

    with (
        patch(_BACKEND, return_value="qt"),
        patch.object(
            streamer._stream_buffer,
            "open",
            new_callable=AsyncMock,
        ) as buffer_mock,
        patch.object(
            streamer,
            "get_stream_url",
            new_callable=AsyncMock,
            return_value=hls,
        ) as url_mock,
    ):
        result = await streamer.open_playback(track)

    assert result == hls
    url_mock.assert_awaited_once_with(track)
    buffer_mock.assert_not_awaited()
    streamer.shutdown()
