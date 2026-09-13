"""Тесты восстановления потока при зависании."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.controllers.playback_controller import PlaybackController
from quantis.models import YandexTrack
from quantis.plugins.event_bus import EventBus
from quantis.providers import PlaylistManager


@pytest.mark.asyncio
async def test_recover_playback_refreshes_source_and_seeks() -> None:
    player = MagicMock()
    player.time = 42_000
    player.current_source = "https://cdn.example/old"

    music = MagicMock()
    music.streamer.invalidate = MagicMock()
    music.streamer.open_playback = AsyncMock(
        return_value="/tmp/quantis_stream/yandex_1.mp3"
    )

    bridge = MagicMock()
    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=EventBus(),
        async_bridge=bridge,
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    playback._current_track = track

    await playback.recover_playback(42_000, reason="stall")

    music.streamer.invalidate.assert_called_once_with(track)
    music.streamer.open_playback.assert_awaited_once_with(track)
    music.streamer.wait_for_more_prefix.assert_not_called()
    bridge.invoke_main.assert_called_once()
    bridge.invoke_main.call_args[0][0]()
    player.play.assert_called_once_with(
        "/tmp/quantis_stream/yandex_1.mp3",
        start_ms=42_000,
    )


@pytest.mark.asyncio
async def test_recover_playback_prepares_buffer_before_replay() -> None:
    player = MagicMock()
    player.time = 42_000
    player.current_source = "/tmp/quantis_stream/yandex_1.mp3"

    music = MagicMock()
    music.streamer.open_playback = AsyncMock(
        return_value="/tmp/quantis_stream/yandex_1.mp3"
    )
    music.streamer.seek_to_ms = AsyncMock()

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=EventBus(),
        async_bridge=MagicMock(),
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    playback._current_track = track

    await playback.recover_playback(42_000, reason="stall")

    music.streamer.seek_to_ms.assert_awaited_once_with(
        track, 42_000, source="/tmp/quantis_stream/yandex_1.mp3"
    )


@pytest.mark.asyncio
async def test_recovery_limit_switches_to_next_track() -> None:
    player = MagicMock()
    player.time = 5_000
    player.current_source = "https://cdn.example/old"

    music = MagicMock()
    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=EventBus(),
        async_bridge=MagicMock(),
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    playback._current_track = track
    playback._stall_track_key = f"{track.source}:{track.track_id}"
    playback._stall_recoveries = 3
    playback.play_next = AsyncMock()  # type: ignore[method-assign]

    await playback.recover_playback(5_000, reason="stall")

    # Раньше плеер просто замолкал и следующий трек не включался.
    playback.play_next.assert_awaited_once()
    music.streamer.open_playback.assert_not_called()


@pytest.mark.asyncio
async def test_seek_waits_for_buffer_then_moves_player() -> None:
    player = MagicMock()
    player.current_source = "/tmp/quantis_stream/yandex_1.mp3"
    player.duration = 180_000

    music = MagicMock()
    music.streamer.seek_to_ms = AsyncMock()
    event_bus = EventBus()
    seeked: list[int] = []
    event_bus.playback_seeked.connect(seeked.append)
    bridge = MagicMock()

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=event_bus,
        async_bridge=bridge,
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    playback._current_track = track

    playback.seek(42_000)
    await bridge.schedule.call_args[0][0]
    bridge.invoke_main.call_args[0][0]()

    music.streamer.seek_to_ms.assert_awaited_once_with(
        track, 42_000, source="/tmp/quantis_stream/yandex_1.mp3"
    )
    assert player.time == 42_000
    assert seeked == [42_000]
    assert playback.is_seeking is False


@pytest.mark.asyncio
async def test_stale_seek_is_dropped_after_track_change() -> None:
    player = MagicMock()
    player.current_source = "/tmp/quantis_stream/yandex_1.mp3"
    player.duration = 180_000

    music = MagicMock()
    music.streamer.seek_to_ms = AsyncMock(return_value=True)
    bridge = MagicMock()
    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=EventBus(),
        async_bridge=bridge,
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    other = YandexTrack(track_id="2", title="Next", author="Artist")
    playback._current_track = track

    playback.seek(42_000)
    seek_coro = bridge.schedule.call_args[0][0]
    playback._begin_track(other)
    await seek_coro

    assert player.time != 42_000


@pytest.mark.asyncio
async def test_seek_near_end_starts_next_track() -> None:
    player = MagicMock()
    player.duration = 180_000
    player.notify_natural_end = MagicMock()

    music = MagicMock()
    music.streamer.seek_to_ms = AsyncMock()
    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=EventBus(),
        async_bridge=MagicMock(),
    )
    playback._current_track = YandexTrack(track_id="1", title="Song", author="Artist")

    playback.seek(179_000)

    player.notify_natural_end.assert_called_once()
    music.streamer.seek_to_ms.assert_not_called()


@pytest.mark.asyncio
async def test_unbuffered_seek_recovers_instead_of_stalling() -> None:
    player = MagicMock()
    player.current_source = "/tmp/quantis_stream/yandex_1.mp3"
    player.duration = 180_000

    music = MagicMock()
    music.streamer.seek_to_ms = AsyncMock(return_value=False)
    bridge = MagicMock()
    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=EventBus(),
        async_bridge=bridge,
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    playback._current_track = track
    playback.request_playback_recovery = MagicMock()  # type: ignore[method-assign]

    playback.seek(42_000)
    await bridge.schedule.call_args[0][0]

    playback.request_playback_recovery.assert_called_once_with(42_000, reason="seek")
    assert playback.is_seeking is False


@pytest.mark.asyncio
async def test_early_recovery_waits_for_more_buffer() -> None:
    player = MagicMock()
    player.time = 800
    player.current_source = "/tmp/quantis_stream/yandex_1.mp3"

    music = MagicMock()
    music.streamer.open_playback = AsyncMock(
        return_value="/tmp/quantis_stream/yandex_1.mp3"
    )
    music.streamer.wait_for_more_prefix = AsyncMock(return_value=True)
    music.streamer.seek_to_ms = AsyncMock(return_value=True)
    bridge = MagicMock()
    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=EventBus(),
        async_bridge=bridge,
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    playback._current_track = track

    await playback.recover_playback(800, reason="ended-early")

    music.streamer.wait_for_more_prefix.assert_awaited_once_with(track)
    music.streamer.seek_to_ms.assert_awaited_once()
    bridge.invoke_main.assert_called_once()
    bridge.invoke_main.call_args[0][0]()
    player.play.assert_called_once_with(
        "/tmp/quantis_stream/yandex_1.mp3",
        start_ms=800,
    )


@pytest.mark.asyncio
async def test_handle_stream_error_uses_paused_position() -> None:
    player = MagicMock()
    player.time = 0
    player.paused_at_ms = 42_000
    player.current_source = "https://cdn.example/old"

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=MagicMock(),
        event_bus=EventBus(),
        async_bridge=MagicMock(),
    )
    playback.request_playback_recovery = MagicMock()  # type: ignore[method-assign]

    playback.handle_stream_error("resume-after-pause")

    playback.request_playback_recovery.assert_called_once_with(
        42_000,
        reason="resume-after-pause",
    )


def test_handle_stream_error_uses_last_known_when_time_resets() -> None:
    player = MagicMock()
    player.time = 0
    player.paused_at_ms = 0
    player.last_known_ms = 10_400
    player.current_source = "https://rr.googlevideo.com/videoplayback"

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=MagicMock(),
        event_bus=EventBus(),
        async_bridge=MagicMock(),
    )
    playback.request_playback_recovery = MagicMock()  # type: ignore[method-assign]

    playback.handle_stream_error("ended-early")

    playback.request_playback_recovery.assert_called_once_with(
        10_400,
        reason="ended-early",
    )
