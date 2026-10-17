"""«Моя волна» без Яндекса: радио YouTube Music по сидам и диспетчер волн."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.models import YandexTrack, YoutubeTrack
from quantis.models.playlist import WavePlaylist
from quantis.services import wave_router
from quantis.services.wave_router import WaveRouter
from quantis.services.youtube_wave import (
    YoutubeWaveService,
    is_taste_wave,
    seed_query,
)


def _vid(n: int) -> str:
    return f"vid{n:08d}"  # 11 символов, как у YouTube


def _watch(*items: tuple[int, str] | tuple[int, str, str]) -> dict:
    tracks = []
    for item in items:
        n, artist, *length = item
        tracks.append(
            {
                "videoId": _vid(n),
                "title": f"Song {n}",
                "artists": [{"name": artist}],
                "length": length[0] if length else "3:00",
            }
        )
    return {"tracks": tracks}


class _FakeYT:
    def __init__(self, search: list[dict], watch: dict[str, dict]) -> None:
        self._search = search
        self._watch = watch
        self.searches: list[str] = []
        self.watches: list[dict[str, Any]] = []

    def search(self, query: str, limit: int = 20) -> list[dict]:
        self.searches.append(query)
        return self._search

    def get_watch_playlist(self, **kwargs: Any) -> dict:
        self.watches.append(kwargs)
        key = kwargs.get("playlistId") or kwargs.get("videoId")
        return self._watch.get(key, {"tracks": []})


def _service(yt: _FakeYT) -> YoutubeWaveService:
    return YoutubeWaveService(SimpleNamespace(executor=None), client=yt)


_CALM_SEARCH = [
    {"resultType": "video", "videoId": _vid(99)},
    {"resultType": "playlist", "browseId": "VLPLcalm"},
]


def test_seed_query_merges_mood_and_activity_without_repeats() -> None:
    assert (
        seed_query(("mood:calm", "activity:work-background"))
        == "спокойная поп музыка для работы"
    )
    assert seed_query(("genre:rusrock",)) == "rusrock"
    assert is_taste_wave(("user:onyourwave",))
    assert is_taste_wave(("diversity:reshuffle_123",))
    assert not is_taste_wave(("mood:calm",))


@pytest.mark.asyncio
async def test_mood_wave_plays_radio_of_found_playlist() -> None:
    yt = _FakeYT(
        _CALM_SEARCH,
        {"PLcalm": _watch((1, "A"), (2, "B"), (3, "C", "1:02:00"))},
    )
    wave = await _service(yt).start_wave(["mood:calm"])

    assert wave is not None
    assert wave.source == "youtube"
    assert wave.seeds == ("mood:calm",)
    assert wave.session_id == "pl:PLcalm"
    # Часовой сборник в волну не попадает
    assert [t.track_id for t in wave.get_tracks()] == [_vid(1), _vid(2)]
    assert wave.get_tracks()[0].duration_ms == 180_000
    assert yt.searches == ["спокойная поп музыка"]
    assert yt.watches == [{"playlistId": "PLcalm", "radio": True, "limit": 25}]


@pytest.mark.asyncio
async def test_official_playlist_wins_and_mix_searches_each_seed() -> None:
    yt = _FakeYT(
        [
            {"resultType": "playlist", "browseId": "VLPLuser"},
            {"resultType": "playlist", "browseId": "VLRDCLAK5uy_one"},
            {"resultType": "playlist", "browseId": "VLRDCLAK5uy_two"},
        ],
        {"RDCLAK5uy_one": _watch((1, "A"))},
    )
    wave = await _service(yt).start_wave(["mood:sad", "activity:road-trip"])

    assert wave is not None
    assert wave.session_id == "pl:RDCLAK5uy_one"
    assert yt.searches == ["sad pop"]


@pytest.mark.asyncio
async def test_empty_radio_tries_next_anchor() -> None:
    yt = _FakeYT(
        [
            {"resultType": "playlist", "browseId": "VLRDCLAK5uy_one"},
            {"resultType": "song", "videoId": _vid(9)},
        ],
        {_vid(9): _watch((1, "A"))},
    )
    wave = await _service(yt).start_wave(["mood:sad"])

    assert wave is not None
    assert wave.session_id == f"v:{_vid(9)}"


@pytest.mark.asyncio
async def test_russian_genres_skip_foreign_official_playlists() -> None:
    yt = _FakeYT(
        [
            {"resultType": "playlist", "browseId": "VLRDCLAK5uy_ukr"},
            {"resultType": "playlist", "browseId": "VLPLsoviet"},
        ],
        {"PLsoviet": _watch((1, "Бернес")), "RDCLAK5uy_ukr": _watch((2, "X"))},
    )
    wave = await _service(yt).start_wave(["genre:soviet"])

    assert wave is not None
    assert wave.session_id == "pl:PLsoviet"


@pytest.mark.asyncio
async def test_taste_wave_starts_from_history_track() -> None:
    liked = YoutubeTrack(track_id=_vid(50), title="Fav", author="Me")
    yt = _FakeYT([], {_vid(50): _watch((1, "A"), (2, "B"))})
    wave = await _service(yt).start_wave(taste=[liked])

    assert wave is not None
    assert wave.seeds == ("user:onyourwave",)
    assert wave.session_id == f"v:{_vid(50)}"
    assert yt.searches == []  # id уже есть — искать не нужно


@pytest.mark.asyncio
async def test_taste_wave_finds_yandex_track_on_youtube() -> None:
    track = YandexTrack(track_id="123", title="Группа крови", author="Кино")
    yt = _FakeYT(
        [{"resultType": "song", "videoId": _vid(7)}],
        {_vid(7): _watch((1, "A"))},
    )
    wave = await _service(yt).start_wave(taste=[track])

    assert wave is not None
    assert wave.session_id == f"v:{_vid(7)}"
    assert yt.searches == ["Группа крови Кино"]


@pytest.mark.asyncio
async def test_wave_without_any_results_is_none() -> None:
    assert await _service(_FakeYT([], {})).start_wave(["mood:sad"]) is None


@pytest.mark.asyncio
async def test_finished_track_seeds_next_batch() -> None:
    yt = _FakeYT(
        _CALM_SEARCH,
        {
            "PLcalm": _watch((1, "A"), (2, "B")),
            _vid(2): _watch((2, "B"), (3, "C"), (4, "D")),
        },
    )
    service = _service(yt)
    wave = await service.start_wave(["mood:calm"])
    assert wave is not None
    first, second = wave.get_tracks()

    nxt = await service.continue_after_finish(wave, first, played_seconds=180)
    assert nxt is second
    await service.notify_track_started(second, wave)
    nxt = await service.continue_after_finish(wave, second, played_seconds=180)

    # Пачка кончилась — радио от последнего дослушанного, без повторов
    assert yt.watches[-1] == {"videoId": _vid(2), "limit": 25}
    assert nxt is not None and nxt.track_id == _vid(3)
    assert [t.track_id for t in wave.get_tracks()] == [_vid(n) for n in (1, 2, 3, 4)]


@pytest.mark.asyncio
async def test_artist_skipped_twice_is_not_played_again() -> None:
    yt = _FakeYT(
        _CALM_SEARCH,
        {"PLcalm": _watch((1, "Nope"), (2, "Nope"), (3, "Nope"), (4, "Yes"))},
    )
    service = _service(yt)
    wave = await service.start_wave(["mood:calm"])
    assert wave is not None
    tracks = wave.get_tracks()

    nxt = await service.continue_after_finish(wave, tracks[0], played_seconds=10)
    assert nxt is tracks[1]  # один скип — ещё не повод
    nxt = await service.continue_after_finish(wave, tracks[1], played_seconds=10)
    assert nxt is tracks[3]


@pytest.mark.asyncio
async def test_extend_falls_back_to_wave_anchor() -> None:
    yt = _FakeYT(
        _CALM_SEARCH,
        {"PLcalm": _watch((1, "A"))},
    )
    service = _service(yt)
    wave = await service.start_wave(["mood:calm"])
    assert wave is not None
    yt._watch["PLcalm"] = _watch((1, "A"), (5, "E"))

    # Скипнули — сида от трека нет, догружаем от плейлиста волны
    nxt = await service.continue_after_finish(
        wave, wave.get_tracks()[0], played_seconds=3
    )
    assert yt.watches[-1]["playlistId"] == "PLcalm"
    assert nxt is not None and nxt.track_id == _vid(5)


# --- диспетчер -------------------------------------------------------------


def _router(monkeypatch, token: str) -> tuple[WaveRouter, MagicMock, MagicMock]:
    monkeypatch.setattr(wave_router, "yandex_token", lambda: token)
    yandex, youtube = MagicMock(), MagicMock()
    yandex.start_yandex_wave = AsyncMock(return_value=None)
    youtube.start_wave = AsyncMock(return_value=None)
    for service in (yandex, youtube):
        service.continue_after_finish = AsyncMock(return_value=None)
        service.fetch_wheel = AsyncMock(return_value=[])
    return WaveRouter(lambda: yandex, lambda: youtube), yandex, youtube


@pytest.mark.asyncio
async def test_router_without_token_uses_youtube(monkeypatch) -> None:
    router, yandex, youtube = _router(monkeypatch, "")
    taste = [YoutubeTrack(track_id=_vid(1), title="t", author="a")]

    await router.start_wave(("mood:calm",), taste=taste)
    await router.fetch_wheel()

    youtube.start_wave.assert_awaited_once_with(("mood:calm",), name=None, taste=taste)
    yandex.start_yandex_wave.assert_not_called()
    yandex.fetch_wheel.assert_not_called()


@pytest.mark.asyncio
async def test_router_falls_back_to_youtube_when_yandex_fails(monkeypatch) -> None:
    router, yandex, youtube = _router(monkeypatch, "token")
    await router.start_wave(("mood:calm",))
    yandex.start_yandex_wave.assert_awaited_once()
    youtube.start_wave.assert_awaited_once()


@pytest.mark.asyncio
async def test_router_continues_wave_with_its_own_source(monkeypatch) -> None:
    router, yandex, youtube = _router(monkeypatch, "token")
    track = YoutubeTrack(track_id=_vid(1), title="t", author="a")
    wave = WavePlaylist(tracks=[track], source="youtube")

    await router.continue_after_finish(wave, track, played_seconds=1)

    youtube.continue_after_finish.assert_awaited_once()
    yandex.continue_after_finish.assert_not_called()
