"""Предзагрузка: YouTube на два трека вперёд, клип фона — для следующего."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.controllers.playback_controller import PlaybackController
from quantis.models import YandexTrack, YoutubeTrack


def _controller(tracks) -> PlaybackController:
    player = MagicMock()
    player.duration = 200_000
    player.time = 5_000
    controller = PlaybackController(
        player=player,
        playlist_manager=MagicMock(),
        music_service=MagicMock(),
        event_bus=None,
        async_bridge=None,
    )
    playlist = MagicMock()
    playlist.__len__.return_value = len(tracks)
    playlist.tracks.values = tuple(tracks)
    controller.playlist_manager.current_playlist = playlist
    controller.music.streamer.prefetch_stream = AsyncMock()
    return controller


def _yt(n: int) -> YoutubeTrack:
    return YoutubeTrack(track_id=f"abcdefghij{n}", title=str(n), author="A")


@pytest.mark.asyncio
async def test_youtube_prefetches_two_ahead_and_announces_next(monkeypatch) -> None:
    tracks = [_yt(0), _yt(1), _yt(2), _yt(3)]
    controller = _controller(tracks)
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "quantis.controllers.playback_controller.asyncio.sleep", fake_sleep
    )
    announced: list = []
    controller.add_upcoming_listener(announced.append)
    await controller._prefetch_next_track(tracks[0])

    assert sleeps == [3.0]
    assert announced == [tracks[1]]
    awaited = [
        c.args[0] for c in controller.music.streamer.prefetch_stream.await_args_list
    ]
    assert awaited == [tracks[1], tracks[2]]


@pytest.mark.asyncio
async def test_yandex_next_still_waits_for_track_end(monkeypatch) -> None:
    current = YandexTrack(track_id="1", title="A", author="A")
    nxt = YandexTrack(track_id="2", title="B", author="A")
    controller = _controller([current, nxt])
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(
        "quantis.controllers.playback_controller.asyncio.sleep", fake_sleep
    )
    announced: list = []
    controller.add_upcoming_listener(announced.append)
    await controller._prefetch_next_track(current)

    assert announced == [nxt]  # клип фона ищется сразу
    # ссылка Яндекса — по-прежнему за 35 с до конца: 195 − 35 − 3 = 157 с
    assert sleeps == [3.0, pytest.approx(157.0)]
    controller.music.streamer.prefetch_stream.assert_awaited_once_with(nxt)
