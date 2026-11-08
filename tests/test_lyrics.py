"""Тексты песен: разбор LRC, выбор из LRCLIB, кэш и вкладка «Текст»."""

from __future__ import annotations

import asyncio

import pytest

from quantis.models.track import YandexTrack, YoutubeTrack
from quantis.services import lyrics as lyrics_mod
from quantis.services.lyrics import (
    LyricLine,
    Lyrics,
    LyricsService,
    artist_title,
    parse_lrc,
    pick_search_result,
)


def test_parse_lrc_sorts_and_splits_repeated_stamps() -> None:
    lines = parse_lrc("[00:10.50]Первая\n[01:00][00:05]Припев\nбез метки\n")
    assert [(line.t, line.text) for line in lines] == [
        (5_000, "Припев"),
        (10_500, "Первая"),
        (60_000, "Припев"),
    ]


def test_line_at_follows_position() -> None:
    lyrics = Lyrics([LyricLine(1_000, "a"), LyricLine(5_000, "b")], synced=True)
    assert lyrics.line_at(0) == -1
    assert lyrics.line_at(1_000) == 0
    assert lyrics.line_at(7_000) == 1
    assert Lyrics([LyricLine(-1, "x")]).line_at(9_000) == -1  # несинхронный


def test_youtube_title_gives_artist() -> None:
    track = YoutubeTrack(
        track_id="v", title="Кино - Группа крови (Official Video)", author="Канал"
    )
    assert artist_title(track) == ("Кино", "Группа крови")
    yandex = YandexTrack(track_id=1, title="A - B", author="Артист")
    assert artist_title(yandex) == ("Артист", "A - B")


def test_pick_search_prefers_close_duration_and_synced() -> None:
    items = [
        {"duration": 300, "syncedLyrics": "[00:01]далёкий"},
        {"duration": 181, "plainLyrics": "простой"},
        {"duration": 182, "syncedLyrics": "[00:01]точный"},
    ]
    found = pick_search_result(items, 180)
    assert found is not None and found.synced
    assert found.lines[0].text == "точный"
    assert pick_search_result([{"duration": 400, "plainLyrics": "x"}], 180) is None


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(lyrics_mod.app_paths, "cache_dir", lambda: tmp_path)
    return tmp_path


def test_fetch_caches_result_and_missing(cache_dir, monkeypatch) -> None:
    calls: list[str] = []

    async def lrclib(self, track):
        calls.append(track.title)
        return (
            Lyrics([LyricLine(0, "строка")], True, "LRCLIB")
            if track.title == "есть"
            else None
        )

    monkeypatch.setattr(LyricsService, "_from_lrclib", lrclib)
    service = LyricsService()
    found = YoutubeTrack(track_id="1", title="есть", author="a")
    missing = YoutubeTrack(track_id="2", title="нет", author="a")
    for _ in range(2):
        assert asyncio.run(service.fetch(found)).lines[0].text == "строка"
        assert asyncio.run(service.fetch(missing)).lines == []
    assert calls == ["есть", "нет"]  # второй раз — из кэша


def test_network_error_is_not_cached(cache_dir, monkeypatch) -> None:
    async def broken(self, track):
        raise TimeoutError

    monkeypatch.setattr(LyricsService, "_from_lrclib", broken)
    track = YoutubeTrack(track_id="3", title="t", author="a")
    assert asyncio.run(LyricsService().fetch(track)).lines == []
    assert lyrics_mod.cached(track) is None


def test_side_panel_tabs(qapp, tmp_path) -> None:
    from quantis.ui.views.widgets.side_panel import SidePanel

    class _Paths:
        def get_cover_path(self, track):
            return str(tmp_path / "none.jpg")

    panel = SidePanel(_Paths())
    asked: list[str] = []
    panel.tab_requested.connect(asked.append)
    panel._tabs["lyrics"].click()
    assert asked == ["lyrics"]
    panel.set_tab("lyrics")
    assert panel.tab() == "lyrics"
    view = panel.lyrics
    view.resize(300, 400)
    view.set_lyrics(
        Lyrics([LyricLine(0, "раз"), LyricLine(2_000, "два")], True, "LRCLIB")
    )
    view.set_position(2_500)
    assert view.current_line == 1
    seeks: list[int] = []
    panel.seek_requested.connect(seeks.append)
    view.seek_requested.emit(0)
    assert seeks == [0]
    view.set_lyrics(Lyrics())
    assert view.state == "missing"


def test_yandex_uses_async_lyrics_download(monkeypatch) -> None:
    """У асинхронного клиента текст качается fetch_lyrics_async: синхронный
    fetch_lyrics падал на assert, и Яндекс молча подменялся LRCLIB."""

    class _TrackLyrics:
        def fetch_lyrics(self):
            raise AssertionError("синхронный вызов на асинхронном клиенте")

        async def fetch_lyrics_async(self):
            return "[00:01.00]строка из Яндекса"

    class _Client:
        async def tracks_lyrics(self, track_id, format_):
            return _TrackLyrics()

    from quantis.config import clients, credentials

    monkeypatch.setattr(credentials, "yandex_token", lambda: "token")
    monkeypatch.setattr(clients.Clients, "get_yandex_client", lambda self: _Client())
    found = asyncio.run(
        LyricsService()._from_yandex(YandexTrack(track_id=1, title="t", author="a"))
    )
    assert found is not None and found.source == "Яндекс Музыка" and found.synced


def test_base_title_drops_version_tails() -> None:
    from quantis.services.lyrics import base_title

    assert base_title("What Is Love (remix)") == "What Is Love"
    assert base_title("What Is Love [Lynx & Pico Remix]") == "What Is Love"
    assert base_title("What Is Love - Extended Mix") == "What Is Love"
    assert base_title("Ват из лав (feat. Кто-то) (Sped Up)") == "Ват из лав"
    assert base_title("Song ft. Someone") == "Song"
    assert base_title("Группа крови") == "Группа крови"  # нечего срезать


def test_pick_loose_gives_plain_text_when_length_differs() -> None:
    """Ремикс длиннее оригинала: текст подходит, а тайминги — нет."""
    items = [{"duration": 270, "syncedLyrics": "[00:01]What is love\n[00:05]Baby"}]
    assert pick_search_result(items, 200) is None
    found = pick_search_result(items, 200, loose=True)
    assert found is not None and not found.synced
    assert [line.text for line in found.lines] == ["What is love", "Baby"]
    assert all(line.t == -1 for line in found.lines)
    close = pick_search_result(items, 271, loose=True)
    assert close is not None and close.synced  # длина совпала — синхронный


def test_remix_falls_back_to_original_lyrics(cache_dir, monkeypatch) -> None:
    asked: list[tuple[str, str]] = []

    async def get(self, http, artist, title, duration):
        return None  # точной записи нет ни для ремикса, ни для оригинала

    async def search(self, http, artist, title):
        asked.append((artist, title))
        if "remix" in title.lower():
            return []
        return [{"duration": 270, "syncedLyrics": "[00:01]What is love"}]

    monkeypatch.setattr(LyricsService, "_lrclib_get", get)
    monkeypatch.setattr(LyricsService, "_lrclib_search", search)
    track = YandexTrack(
        track_id=7, title="What Is Love (remix)", author="Haddaway", duration_ms=200_000
    )
    found = asyncio.run(LyricsService().fetch(track))
    assert [line.text for line in found.lines] == ["What is love"]
    assert not found.synced
    assert asked == [("Haddaway", "What Is Love (remix)"), ("Haddaway", "What Is Love")]


def test_old_cached_miss_is_retried(cache_dir) -> None:
    """«Не нашлось» из старой версии поиска не держим вечно."""
    track = YoutubeTrack(track_id="old", title="t", author="a")
    lyrics_mod._cache_path(track).write_text(
        '{"lines": [], "synced": false, "source": ""}', encoding="utf-8"
    )
    assert lyrics_mod.cached(track) is None
    lyrics_mod._store(track, Lyrics())
    assert lyrics_mod.cached(track) is not None  # новая запись — из кэша
