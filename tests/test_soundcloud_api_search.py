"""Поиск SoundCloud через api-v2: DRM и заблокированные треки не попадают в выдачу."""

from __future__ import annotations

from quantis.services.soundcloud import track_from_api


def _item(**extra) -> dict:
    item = {
        "kind": "track",
        "id": 123,
        "title": "Song",
        "full_duration": 201_000,
        "artwork_url": "https://i1.sndcdn.com/artworks-x-large.jpg",
        "user": {"username": "Artist"},
        "media": {"transcodings": [{"format": {"protocol": "progressive"}}]},
    }
    item.update(extra)
    return item


def test_playable_track_is_parsed() -> None:
    track = track_from_api(_item())
    assert track is not None
    assert track.track_id == "123"
    assert track.author == "Artist"
    assert track.duration_ms == 201_000
    assert track.thumbnail_url.endswith("-t500x500.jpg")


def test_drm_only_track_is_skipped() -> None:
    media = {"transcodings": [{"format": {"protocol": "ctr-encrypted-hls"}}]}
    assert track_from_api(_item(media=media)) is None


def test_blocked_and_non_tracks_are_skipped() -> None:
    assert track_from_api(_item(policy="BLOCK")) is None
    assert track_from_api(_item(kind="playlist")) is None
    assert track_from_api(None) is None
