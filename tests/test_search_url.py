"""Поиск по прямой ссылке не разбивает ролик на чужие результаты."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.models import SoundCloudTrack, YoutubeTrack
from quantis.ui.viewmodels.search_vm import SearchViewModel


@pytest.mark.asyncio
async def test_youtube_url_resolves_single_track(qapp) -> None:
    finder = MagicMock()
    track = YoutubeTrack(
        track_id="nFywCgAlUnE",
        title="CHILL PHONK MIX",
        author="NEMI",
    )
    finder.resolve_tracks = AsyncMock(return_value=[track])
    playback = MagicMock()
    bridge = MagicMock()
    bridge.invoke_main.side_effect = lambda fn: fn()

    vm = SearchViewModel(finder, playback, bridge)
    url = "https://www.youtube.com/watch?v=nFywCgAlUnE"
    await vm._search_async(url, vm._search_generation)

    finder.resolve_tracks.assert_awaited_once_with(url=url)
    finder.iter_track_batches.assert_not_called()
    assert vm.model.rowCount() == 1
    assert vm.model.get_track(0) is track


@pytest.mark.asyncio
async def test_soundcloud_url_resolves_single_track(qapp) -> None:
    finder = MagicMock()
    track = SoundCloudTrack(
        track_id="123456",
        title="CHILL PHONK MIX",
        author="NEMI",
    )
    finder.resolve_tracks = AsyncMock(return_value=[track])
    playback = MagicMock()
    bridge = MagicMock()
    bridge.invoke_main.side_effect = lambda fn: fn()

    vm = SearchViewModel(finder, playback, bridge)
    url = "https://soundcloud.com/nemi/chill-phonk-mix"
    await vm._search_async(url, vm._search_generation)

    finder.resolve_tracks.assert_awaited_once_with(url=url)
    finder.iter_track_batches.assert_not_called()
    assert vm.model.rowCount() == 1
    assert vm.model.get_track(0) is track
