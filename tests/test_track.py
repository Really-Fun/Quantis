from __future__ import annotations

import pytest

from quantis.models import SoundCloudTrack, YandexTrack, YoutubeTrack
from quantis.services import AsyncFinder

pytestmark = pytest.mark.asyncio


@pytest.mark.network
async def test_find_track_from_yandex():
    finder = AsyncFinder()
    tracks = await finder.get_tracks("Intro alt-j", value=1)
    assert isinstance(tracks, list)
    assert len(tracks) >= 1
    assert any(isinstance(track, YandexTrack) for track in tracks)


@pytest.mark.network
async def test_find_track_from_youtube():
    finder = AsyncFinder()

    tracks = await finder.get_tracks("Intro alt-j", value=1)
    assert isinstance(tracks, list)
    assert len(tracks) >= 1
    assert any(isinstance(track, YoutubeTrack) for track in tracks)


@pytest.mark.network
async def test_find_track_from_soundcloud():
    finder = AsyncFinder()
    tracks = await finder.get_tracks("Intro alt-j", value=1)
    assert isinstance(tracks, list)
    assert len(tracks) >= 1
    assert any(isinstance(track, SoundCloudTrack) for track in tracks)
