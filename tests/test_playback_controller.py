"""Unit-тесты PlaybackController (без сети)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.controllers.playback_controller import PlaybackController
from quantis.models import YandexTrack
from quantis.models.playlist import RecommendationPlaylist, WavePlaylist
from quantis.plugins.event_bus import EventBus
from quantis.providers import PlaylistManager


@pytest.mark.asyncio
async def test_play_track_sets_current_and_emits_event() -> None:
    player = MagicMock()
    music = MagicMock()
    music.streamer.open_playback = AsyncMock(return_value="http://stream")
    music.provider.get_track_path = MagicMock(return_value="/path")
    event_bus = EventBus()
    bridge = MagicMock()

    emitted: list[object] = []
    event_bus.track_changed.connect(emitted.append)

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=event_bus,
        history=None,
        async_bridge=bridge,
    )

    track = YandexTrack(track_id="1", title="Song", author="Artist")
    await playback.play_track(track)

    bridge.invoke_main.assert_called()
    for call in bridge.invoke_main.call_args_list:
        call[0][0]()

    assert playback.current_track is track
    assert player.current_track is track
    player.play.assert_called_once_with("http://stream")
    assert emitted == [track]


@pytest.mark.asyncio
async def test_play_track_announces_before_source_is_ready() -> None:
    player = MagicMock()
    music = MagicMock()
    announced: list[object] = []
    opened: list[list[object]] = []

    async def slow_open(track):
        opened.append(list(announced))
        return "http://stream"

    music.streamer.open_playback = slow_open
    music.provider.get_track_path = MagicMock(return_value="/path")
    event_bus = EventBus()
    event_bus.track_changed.connect(announced.append)
    bridge = MagicMock()
    bridge.invoke_main.side_effect = lambda cb: cb()
    scheduled: list = []
    bridge.schedule = scheduled.append

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=event_bus,
        history=None,
        async_bridge=bridge,
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    await playback.play_track(track)
    for coro in scheduled:
        await coro

    assert opened == [[track]]
    player.stop.assert_called()
    player.play.assert_called_once_with("http://stream")


@pytest.mark.asyncio
async def test_play_track_starts_from_beginning() -> None:
    player = MagicMock()
    music = MagicMock()
    music.streamer.open_playback = AsyncMock(return_value="https://cdn.example/a.mp3")
    music.provider.get_track_path = MagicMock(return_value="/path")
    history = MagicMock()
    history.get_resume_position = AsyncMock(return_value=15_000)
    event_bus = EventBus()

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=event_bus,
        history=history,
        async_bridge=None,
    )

    track = YandexTrack(track_id="1", title="Song", author="Artist")
    await playback.play_track(track)

    history.get_resume_position.assert_not_called()
    player.play.assert_called_once_with("https://cdn.example/a.mp3")


@pytest.mark.asyncio
async def test_play_track_starts_before_wave_feedback() -> None:
    player = MagicMock()
    order: list[str] = []

    async def notify(*_args, **_kwargs):
        order.append("notify")

    music = MagicMock()
    music.streamer.open_playback = AsyncMock(return_value="http://stream")
    music.provider.get_track_path = MagicMock(return_value="/path")
    music.wave.notify_track_started = notify
    player.play.side_effect = lambda *_args, **_kwargs: order.append("play")

    manager = PlaylistManager()
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    previous = manager.current_playlist
    manager.set_playlist(WavePlaylist(tracks=[track], source="yandex"))
    playback = PlaybackController(
        player=player,
        playlist_manager=manager,
        music_service=music,
        event_bus=EventBus(),
        async_bridge=None,
    )
    try:
        await playback.play_track(track)
    finally:
        manager.set_playlist(previous)

    assert order == ["play", "notify"]


@pytest.mark.asyncio
async def test_prefetch_next_track_uses_upgrade_cycle() -> None:
    player = MagicMock()
    music = MagicMock()
    music.streamer.prefetch_stream = AsyncMock()
    manager = PlaylistManager()
    previous = manager.current_playlist
    t1 = YandexTrack(track_id="1", title="One", author="A")
    t2 = YandexTrack(track_id="2", title="Two", author="A")
    manager.set_playlist(RecommendationPlaylist(tracks=[t1, t2]))
    playback = PlaybackController(
        player=player,
        playlist_manager=manager,
        music_service=music,
    )
    try:
        await playback._prefetch_next_track(t1)
    finally:
        manager.set_playlist(previous)

    music.streamer.prefetch_stream.assert_awaited_once_with(t2)
