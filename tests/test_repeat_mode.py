"""Тесты режима повтора и завершения трека."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.controllers.playback_controller import PlaybackController
from quantis.models import YandexTrack
from quantis.models.playlist import UserPlaylist
from quantis.models.repeat_mode import RepeatMode
from quantis.plugins.event_bus import EventBus
from quantis.providers import PlaylistManager


@pytest.mark.asyncio
async def test_handle_track_finished_replays_track_in_track_mode() -> None:
    player = MagicMock()
    music = MagicMock()
    music.streamer.open_playback = AsyncMock(return_value="http://stream")
    music.provider.get_track_path = MagicMock(return_value="/path")
    event_bus = EventBus()
    bridge = MagicMock()

    playback = PlaybackController(
        player=player,
        playlist_manager=PlaylistManager(),
        music_service=music,
        event_bus=event_bus,
        history=None,
        async_bridge=bridge,
    )
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    playback._current_track = track
    playback._repeat_mode = RepeatMode.TRACK
    bridge.invoke_main.side_effect = lambda fn: fn()

    await playback.handle_track_finished()

    music.streamer.open_playback.assert_awaited_once_with(track)


@pytest.mark.asyncio
async def test_handle_track_finished_advances_in_playlist_mode() -> None:
    player = MagicMock()
    music = MagicMock()
    music.streamer.open_playback = AsyncMock(return_value="http://stream")
    music.provider.get_track_path = MagicMock(return_value="/path")
    music.wave = MagicMock()
    event_bus = EventBus()
    bridge = MagicMock()

    playlists = PlaylistManager()
    t1 = YandexTrack(track_id="1", title="One", author="A")
    t2 = YandexTrack(track_id="2", title="Two", author="B")
    playlist = UserPlaylist("Test", [t1, t2])
    playlists.set_playlist(playlist)
    playlist.set_current_track(0)

    playback = PlaybackController(
        player=player,
        playlist_manager=playlists,
        music_service=music,
        event_bus=event_bus,
        history=None,
        async_bridge=bridge,
    )
    playback._current_track = t1
    playback._repeat_mode = RepeatMode.PLAYLIST
    bridge.invoke_main.side_effect = lambda fn: fn()

    await playback.handle_track_finished()

    assert music.streamer.open_playback.await_count == 1
    music.streamer.open_playback.assert_awaited_with(t2)
    assert playback.current_track is t2


def test_repeat_mode_cycles_playlist_and_track() -> None:
    assert RepeatMode.PLAYLIST.cycle() is RepeatMode.TRACK
    assert RepeatMode.TRACK.cycle() is RepeatMode.PLAYLIST
