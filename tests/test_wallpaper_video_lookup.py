"""Видео для фона трека Яндекса ищется только на YouTube и один раз."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from quantis.models import YandexTrack, YoutubeTrack
from quantis.services.async_streamer import AsyncStreamer


class _Finder:
    def __init__(self) -> None:
        self.youtube = AsyncMock()
        self.youtube.get_tracks = AsyncMock(
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
    finder.youtube.get_tracks.assert_awaited_once()
