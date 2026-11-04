"""Видео для фона трека Яндекса ищется только на YouTube и один раз."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from quantis.models import YandexTrack, YoutubeTrack
from quantis.services.async_streamer import AsyncStreamer


class _Finder:
    def __init__(self) -> None:
        self.youtube = AsyncMock()
        self.youtube.search_videos = AsyncMock(
            return_value=[YoutubeTrack(track_id="abcdefghijk", title="T", author="A")]
        )
        self.get_tracks = AsyncMock(side_effect=AssertionError("общий поиск"))


@pytest.mark.asyncio
async def test_lookup_uses_youtube_only_and_is_cached() -> None:
    streamer = AsyncStreamer()
    finder = _Finder()
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    for _ in range(3):
        video_id = await streamer._resolve_youtube_video_id(track, finder)
        assert video_id == "abcdefghijk"
    finder.youtube.search_videos.assert_awaited_once()


def _clip(video_id: str, seconds: int) -> YoutubeTrack:
    return YoutubeTrack(
        track_id=video_id, title="T", author="A", duration_ms=seconds * 1000
    )


def test_clip_of_the_same_length_wins_over_first_result() -> None:
    from quantis.services.async_streamer import pick_wallpaper_clip

    long_intro = _clip("aaaaaaaaaaa", 184)
    same = _clip("bbbbbbbbbbb", 169)
    assert pick_wallpaper_clip([long_intro, same], 168_280) is same


def test_first_clip_when_none_match_length_or_length_unknown() -> None:
    from quantis.services.async_streamer import pick_wallpaper_clip

    official, live = _clip("aaaaaaaaaaa", 184), _clip("bbbbbbbbbbb", 177)
    assert pick_wallpaper_clip([official, live], 168_000) is official
    assert pick_wallpaper_clip([official, live], 0) is official
    assert pick_wallpaper_clip([], 1000) is None


@pytest.mark.asyncio
async def test_lookup_retries_with_title_only() -> None:
    from quantis.models import SoundCloudTrack

    streamer = AsyncStreamer()
    finder = _Finder()
    hit = YoutubeTrack(track_id="abcdefghijk", title="T", author="A")
    finder.youtube.search_videos = AsyncMock(side_effect=[[], [hit]])
    track = SoundCloudTrack(track_id="5", title="Кино - Пачка", author="uploader")
    assert await streamer._resolve_youtube_video_id(track, finder) == "abcdefghijk"
    queries = [c.args[0] for c in finder.youtube.search_videos.await_args_list]
    assert queries == ["Кино - Пачка uploader", "Кино - Пачка"]
