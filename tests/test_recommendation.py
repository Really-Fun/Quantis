"""Плейлист рекомендаций: пачки по 5 с YouTube и догрузка в конце."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.controllers.playback_controller import PlaybackController
from quantis.models import YoutubeTrack
from quantis.models.playlist import RecommendationPlaylist
from quantis.plugins.event_bus import EventBus
from quantis.providers import PlaylistManager
from quantis.services.async_recommendation import BATCH_SIZE, AsyncRecommendation


def _yt(video_id: str, title: str = "T") -> YoutubeTrack:
    return YoutubeTrack(track_id=video_id, title=title, author="A")


def test_append_tracks_skips_duplicates() -> None:
    t1 = _yt("abcdefghijk", "One")
    playlist = RecommendationPlaylist(tracks=[t1], infinite=True)
    added = playlist.append_tracks([t1, _yt("bcdefghijkl", "Two")])
    assert added == 1
    assert len(playlist) == 2


def test_take_seed_rotates_history() -> None:
    s1, s2 = _yt("seed1111111", "S1"), _yt("seed2222222", "S2")
    playlist = RecommendationPlaylist(seeds=(s1, s2), infinite=True)
    assert playlist.take_seed(s1) is s1
    assert playlist.take_seed(s1) is s2
    assert playlist.take_seed(s1) is s1


def test_tracks_from_watch_skips_seed_and_caps_batch() -> None:
    service = AsyncRecommendation(youtube_finder=MagicMock())
    seed_id = "seedvideo11"
    payload = {
        "tracks": [
            {"videoId": seed_id, "title": "Seed", "artists": [{"name": "A"}]},
            *[
                {
                    "videoId": f"rec{i:08d}",
                    "title": f"Rec {i}",
                    "artists": [{"name": "B"}],
                    "duration": "3:21",
                }
                for i in range(8)
            ],
        ]
    }
    tracks = service._tracks_from_watch(
        payload, limit=BATCH_SIZE, exclude_ids={seed_id}
    )
    assert len(tracks) == 5
    assert all(str(t.track_id) != seed_id for t in tracks)
    assert tracks[0].title == "Rec 0"


@pytest.mark.asyncio
async def test_generate_from_history_uses_watch_playlist() -> None:
    finder = MagicMock()
    finder.executor = None
    client = MagicMock()
    client.get_watch_playlist.return_value = {
        "tracks": [
            {"videoId": "abcdefghijk", "title": "Seed", "artists": [{"name": "A"}]},
            {
                "videoId": "bcdefghijkl",
                "title": "Next",
                "artists": [{"name": "B"}],
                "lengthSeconds": 90,
            },
        ]
    }
    service = AsyncRecommendation(youtube_finder=finder, client=client)
    seed = _yt("abcdefghijk", "Seed")
    playlist = await service.generate_from_history([seed])
    assert playlist.infinite is True
    assert playlist.name == "Рекомендации"
    assert [t.track_id for t in playlist.tracks.values] == ["bcdefghijkl"]
    client.get_watch_playlist.assert_called_once()


@pytest.mark.asyncio
async def test_continue_after_finish_appends_when_last() -> None:
    finder = MagicMock()
    finder.executor = None
    client = MagicMock()
    client.get_watch_playlist.return_value = {
        "tracks": [
            {
                "videoId": "newtrack111",
                "title": "More",
                "artists": [{"name": "C"}],
                "duration": "4:00",
            }
        ]
    }
    service = AsyncRecommendation(youtube_finder=finder, client=client)
    t1 = _yt("track111111", "One")
    t2 = _yt("track222222", "Two")
    playlist = RecommendationPlaylist(
        tracks=[t1, t2],
        seeds=(t1,),
        infinite=True,
    )
    playlist.set_current_track(1)
    nxt = await service.continue_after_finish(playlist, t2)
    assert nxt is not None
    assert nxt.track_id == "newtrack111"
    assert len(playlist) == 3
    assert playlist.get_current_track() is nxt


@pytest.mark.asyncio
async def test_play_next_extends_infinite_recommendation_playlist() -> None:
    player = MagicMock()
    music = MagicMock()
    music.streamer.open_playback = AsyncMock(return_value="http://stream")
    music.provider.get_track_path = MagicMock(return_value="/path")
    extra = _yt("zzzzzzzzzzz", "Six")

    async def continue_after_finish(playlist, finished):
        playlist.append_tracks([extra])
        playlist.set_current_track(len(playlist) - 1)
        return extra

    music.recommendation.continue_after_finish = continue_after_finish
    manager = PlaylistManager()
    previous = manager.current_playlist
    tracks = [
        _yt("aaaaaaa0001", "T1"),
        _yt("aaaaaaa0002", "T2"),
        _yt("aaaaaaa0003", "T3"),
        _yt("aaaaaaa0004", "T4"),
        _yt("aaaaaaa0005", "T5"),
    ]
    playlist = RecommendationPlaylist(tracks=tracks, infinite=True)
    playlist.set_current_track(4)
    manager.set_playlist(playlist)
    playback = PlaybackController(
        player=player,
        playlist_manager=manager,
        music_service=music,
        event_bus=EventBus(),
        async_bridge=None,
    )
    playback._current_track = tracks[4]
    try:
        await playback.play_next()
    finally:
        manager.set_playlist(previous)

    assert playback.current_track is extra
    assert len(playlist) == 6


@pytest.mark.asyncio
async def test_play_next_does_not_extend_finite_recommendation_queue() -> None:
    player = MagicMock()
    music = MagicMock()
    music.streamer.open_playback = AsyncMock(return_value="http://stream")
    music.provider.get_track_path = MagicMock(return_value="/path")
    music.recommendation.continue_after_finish = AsyncMock()
    manager = PlaylistManager()
    previous = manager.current_playlist
    t1 = _yt("aaaaaaa0001", "One")
    t2 = _yt("aaaaaaa0002", "Two")
    playlist = RecommendationPlaylist(name="Поиск", tracks=[t1, t2], infinite=False)
    playlist.set_current_track(0)
    manager.set_playlist(playlist)
    playback = PlaybackController(
        player=player,
        playlist_manager=manager,
        music_service=music,
        event_bus=EventBus(),
        async_bridge=None,
    )
    playback._current_track = t1
    try:
        await playback.play_next()
    finally:
        manager.set_playlist(previous)

    music.recommendation.continue_after_finish.assert_not_called()
    assert playback.current_track is t2
