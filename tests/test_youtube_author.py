"""Автор YouTube-трека, в том числе каналы «... - Topic»."""

from __future__ import annotations

from unittest.mock import MagicMock

from quantis.services.async_finder import (
    AsyncYoutubeFinder,
    youtube_author_from_payload,
)


def test_topic_channel_falls_back_to_author_field() -> None:
    assert (
        youtube_author_from_payload(
            {
                "artists": None,
                "author": "The Weeknd - Topic",
                "title": "Blinding Lights",
            }
        )
        == "The Weeknd"
    )


def test_search_artists_list() -> None:
    assert (
        youtube_author_from_payload(
            {
                "artists": [{"name": "The Weeknd", "id": "UC123"}],
                "author": None,
            }
        )
        == "The Weeknd"
    )


def test_strips_topic_and_dedupes_channel() -> None:
    assert (
        youtube_author_from_payload(
            {
                "artists": [{"name": "The Weeknd"}],
                "uploader": "The Weeknd - Topic",
                "channel": "The Weeknd",
            }
        )
        == "The Weeknd"
    )


def test_empty_payload_is_unknown() -> None:
    assert youtube_author_from_payload({}) == "Unknown Artist"
    assert youtube_author_from_payload(None) == "Unknown Artist"


def test_get_song_topic_track_is_playable() -> None:
    finder = AsyncYoutubeFinder(executor=MagicMock())
    finder._client = MagicMock()
    finder._client.get_song.return_value = {
        "videoDetails": {
            "videoId": "J7p4bzqLvCw",
            "title": "Blinding Lights",
            "author": "The Weeknd - Topic",
            "artists": None,
            "lengthSeconds": "200",
        }
    }
    track = finder._sync_get_track("J7p4bzqLvCw")
    assert track is not None
    assert track.track_id == "J7p4bzqLvCw"
    assert track.author == "The Weeknd"
    assert track.title == "Blinding Lights"
    assert track.duration_ms == 200_000


def test_search_skips_rows_without_video_id() -> None:
    finder = AsyncYoutubeFinder(executor=MagicMock())
    finder._client = MagicMock()
    finder._client.search.return_value = [
        {
            "title": "Missing id",
            "videoId": None,
            "artists": [{"name": "X"}],
        },
        {
            "title": "Ok",
            "videoId": "abcdefghijk",
            "artists": [{"name": "Artist"}],
            "duration_seconds": 90,
        },
    ]
    tracks = finder._sync_get_tracks("query", value=5)
    assert len(tracks) == 1
    assert tracks[0].track_id == "abcdefghijk"
    assert tracks[0].author == "Artist"
