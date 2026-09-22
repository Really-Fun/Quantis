"""Unit-тесты парсинга URL для расширенного поиска."""

from __future__ import annotations

from quantis.services.url_resolver import (
    detect_source,
    is_youtube_video_id,
    parse_soundcloud_track_id,
    parse_track_id,
    parse_yandex_track_id,
    parse_youtube_video_id,
)


def test_detect_source_yandex() -> None:
    assert detect_source("https://music.yandex.ru/album/1/track/12345") == "yandex"


def test_detect_source_youtube() -> None:
    assert detect_source("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "youtube"
    assert detect_source("https://youtu.be/dQw4w9WgXcQ") == "youtube"


def test_parse_yandex_track_id() -> None:
    url = "https://music.yandex.ru/album/123/track/987654"
    assert parse_yandex_track_id(url) == "987654"


def test_parse_youtube_video_id_watch() -> None:
    assert (
        parse_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_parse_youtube_video_id_short() -> None:
    assert parse_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_parse_track_id_yandex() -> None:
    parsed = parse_track_id("https://music.yandex.ru/track/555")
    assert parsed == ("yandex", "555")


def test_parse_track_id_youtube() -> None:
    parsed = parse_track_id("https://music.youtube.com/watch?v=abc12345678")
    assert parsed == ("youtube", "abc12345678")


def test_parse_track_id_invalid() -> None:
    assert parse_track_id("https://example.com/foo") is None


def test_detect_source_soundcloud() -> None:
    assert detect_source("https://soundcloud.com/artist/track-name") == "soundcloud"
    assert detect_source("https://m.soundcloud.com/artist/track-name") == "soundcloud"
    assert detect_source("https://on.soundcloud.com/AbCdE") == "soundcloud"


def test_parse_soundcloud_permalink() -> None:
    assert (
        parse_soundcloud_track_id("https://soundcloud.com/artist/track-name")
        == "artist/track-name"
    )


def test_parse_soundcloud_api_id() -> None:
    url = "https://api.soundcloud.com/tracks/123456"
    assert parse_soundcloud_track_id(url) == "123456"


def test_parse_soundcloud_skips_sets_and_profiles() -> None:
    assert parse_soundcloud_track_id("https://soundcloud.com/artist/sets/album") is None
    assert parse_soundcloud_track_id("https://soundcloud.com/artist") is None


def test_parse_track_id_soundcloud() -> None:
    parsed = parse_track_id("https://soundcloud.com/nemi/chill-phonk")
    assert parsed == ("soundcloud", "nemi/chill-phonk")


def test_is_youtube_video_id() -> None:
    assert is_youtube_video_id("dQw4w9WgXcQ")
    assert not is_youtube_video_id("vid")
    assert not is_youtube_video_id("dQw4w9WgXcQ&list=evil")
    assert not is_youtube_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ")
