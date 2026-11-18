"""Субтитры и переводы с настоящей структурой метаданных yt-dlp."""

from __future__ import annotations

import asyncio
import io
import json
import pytest

from quantis.models.track import YoutubeTrack
from quantis.services import lyrics, net_proxy, youtube_captions
from quantis.services.lyrics import LyricLine, Lyrics, LyricsService


def test_fetch_selects_original_and_translation_and_caches_separately(
    tmp_path, monkeypatch
):
    track = YoutubeTrack("video", "Song", "Artist")
    monkeypatch.setattr(lyrics.app_paths, "cache_dir", lambda: tmp_path)
    monkeypatch.setattr(net_proxy, "_proxy", "socks5://localhost:1080")
    monkeypatch.setattr(youtube_captions, "youtube_yt_dlp_cookiefile", lambda: None)
    requests = []

    def fmt(lang, name, target=""):
        url = f"https://www.youtube.com/api/timedtext?lang={lang}"
        if target:
            url += f"&tlang={target}"
        return [{"ext": "json3", "name": name, "url": url}]

    class FakeYoutubeDL:
        def __init__(self, options):
            assert options["writeautomaticsub"]
            assert options["proxy"] == "socks5h://localhost:1080"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download, process):
            assert url.endswith("?v=video") and not download
            return {
                "subtitles": {"de": fmt("de", "Deutsch")},
                "automatic_captions": {
                    "en-orig": fmt("en", "English (original)"),
                    "en": fmt("en", "English"),
                    "ru-de": fmt("de", "Russian from German", "ru"),
                    "ru": fmt("en", "Russian", "ru"),
                },
            }

        def urlopen(self, request):
            requests.append(request.url)
            word = "перевод" if "tlang=" in request.url else "lyric"
            events = [
                {"tStartMs": 412, "segs": [{"utf8": word}, {"utf8": " &amp;"}]},
                {"tStartMs": 3000, "segs": [{"utf8": "\n"}]},
            ]
            return io.BytesIO(json.dumps({"events": events}).encode())

    monkeypatch.setattr(youtube_captions, "YoutubeDL", FakeYoutubeDL)
    service = LyricsService()
    for _ in range(2):
        original = asyncio.run(service.fetch(track, youtube_captions=True))
        assert original.lines == [LyricLine(412, "lyric &")]
        assert original.synced and original.source == "YouTube"
        assert original.translations == {"ru": "Russian", "de": "Deutsch"}
        translated = asyncio.run(service.fetch(track, "ru", youtube_captions=True))
        assert translated.lines == [LyricLine(412, "перевод &")]
    assert [url.split("?")[1] for url in requests] == ["lang=en", "lang=en&tlang=ru"]
    assert not asyncio.run(service.fetch(track, "fr", youtube_captions=True)).lines


def test_temporary_caption_failure_retries_without_losing_offline_lyrics(
    tmp_path, monkeypatch
):
    track = YoutubeTrack("video", "Song", "Artist")
    monkeypatch.setattr(lyrics.app_paths, "cache_dir", lambda: tmp_path)
    old = Lyrics([LyricLine(-1, "saved")], False, "LRCLIB")
    lyrics._store(track, old)
    path = lyrics._cache_path(track)
    path.write_text(json.dumps({**json.loads(path.read_text()), "v": 2}))

    def offline(*args):
        raise TimeoutError

    monkeypatch.setattr(youtube_captions, "fetch_captions", offline)
    assert asyncio.run(LyricsService().fetch(track, youtube_captions=True)) == old
    assert not asyncio.run(
        LyricsService().fetch(track, "ru", youtube_captions=True)
    ).lines

    caption = Lyrics([LyricLine(250, "restored")], True, "YouTube")
    monkeypatch.setattr(youtube_captions, "fetch_captions", lambda *args: caption)
    assert asyncio.run(LyricsService().fetch(track, youtube_captions=True)) == caption


def test_first_lrclib_fallback_is_available_offline_and_youtube_is_retried(
    tmp_path, monkeypatch
):
    track = YoutubeTrack("video", "Song", "Artist")
    monkeypatch.setattr(lyrics.app_paths, "cache_dir", lambda: tmp_path)
    attempts = []

    def offline(*args):
        attempts.append("youtube")
        raise TimeoutError

    async def fallback(self, track):
        attempts.append("lrclib")
        return Lyrics([LyricLine(-1, "saved")], False, "LRCLIB")

    monkeypatch.setattr(youtube_captions, "fetch_captions", offline)
    monkeypatch.setattr(LyricsService, "_from_lrclib", fallback)
    for _ in range(2):
        assert (
            asyncio.run(LyricsService().fetch(track, youtube_captions=True)).source
            == "LRCLIB"
        )
    assert attempts == ["youtube", "lrclib", "youtube"]


def test_automatic_translation_of_manual_track_uses_target_language_code():
    def fmt(query):
        return [
            {"ext": "json3", "url": f"https://www.youtube.com/api/timedtext?{query}"}
        ]

    _, choices = youtube_captions._caption_choices(
        {
            "subtitles": {"en": fmt("lang=en")},
            "automatic_captions": {"zh-Hans-en": fmt("lang=en&tlang=zh-Hans-en")},
        }
    )
    assert list(choices) == ["zh-Hans"]
    assert choices["zh-Hans"]["url"].endswith("lang=en&tlang=zh-Hans")


def test_disabled_by_default_skips_cached_captions_and_youtube(tmp_path, monkeypatch):
    track = YoutubeTrack("video", "Song", "Artist")
    monkeypatch.setattr(lyrics.app_paths, "cache_dir", lambda: tmp_path)
    original = Lyrics([LyricLine(42, "caption")], True, "YouTube", {"ru": "Russian"})
    lyrics._store(track, original)
    monkeypatch.setattr(
        youtube_captions,
        "fetch_captions",
        lambda *_: pytest.fail("unexpected YouTube request"),
    )

    async def regular_lyrics(self, track):
        return Lyrics([LyricLine(-1, "lyrics")], False, "LRCLIB")

    monkeypatch.setattr(LyricsService, "_from_lrclib", regular_lyrics)
    service = LyricsService()
    assert asyncio.run(service.fetch(track)).source == "LRCLIB"
    assert asyncio.run(service.fetch(track, "ru")) == Lyrics()
    assert asyncio.run(service.fetch(track, youtube_captions=True)) == original
