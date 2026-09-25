"""Автор YouTube-трека, в том числе каналы «... - Topic»."""

from __future__ import annotations

from unittest.mock import MagicMock

from quantis.models.track import YoutubeTrack, strip_youtube_stats
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


def test_likes_counter_is_not_an_artist() -> None:
    track = YoutubeTrack(
        track_id="abc", title="t", author='37R, Отметок "Нравится": 1,2 тыс.'
    )
    assert track.author == "37R"


def test_likes_counter_from_downloaded_filename() -> None:
    # в имени файла кавычки и двоеточие заменены на «_»
    track = YoutubeTrack(
        track_id="abc", title="t", author="Narvent, VØJ, Отметок _Нравится__ 174 тыс"
    )
    assert track.author == "Narvent, VØJ"


def test_views_counter_in_english() -> None:
    assert strip_youtube_stats("Narvent | 1.2M views") == "Narvent"


def test_real_artists_are_kept() -> None:
    assert strip_youtube_stats("Likes, Views & Co") == "Likes, Views & Co"
    assert strip_youtube_stats("Tyler, The Creator") == "Tyler, The Creator"
    assert strip_youtube_stats("") == ""
