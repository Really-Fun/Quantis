"""«Моя волна» на сессиях /rotor/session и колесо настроений /wheel/new."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from quantis.models.playlist import WavePlaylist
from quantis.services import async_wave
from quantis.services.async_wave import AsyncWaveService, WaveMood


def _raw_track(track_id: str, album_id: int, duration_ms: int = 200_000) -> dict:
    return {
        "id": track_id,
        "title": f"Song {track_id}",
        "artists": [{"id": 1, "name": "Artist"}],
        "albums": [{"id": album_id, "title": "Album"}],
        "durationMs": duration_ms,
    }


def _session(session_id: str, batch_id: str, *tracks: dict) -> dict:
    return {
        "radioSessionId": session_id,
        "batchId": batch_id,
        "sequence": [{"type": "track", "track": t, "liked": False} for t in tracks],
        "wave": {"name": "Сохранять спокойствие", "seeds": ["mood:calm"]},
    }


class _FakeClient:
    base_url = "https://api.music.yandex.net"
    report_unknown_fields = False

    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict]] = []
        self._request = self
        self.play_audio = AsyncMock()

    async def post(self, url: str, json: dict) -> Any:
        path = url.removeprefix(self.base_url)
        self.calls.append((path, json))
        result = self.responses.get(path)
        if isinstance(result, Exception):
            raise result
        return result

    def paths(self) -> list[str]:
        return [path for path, _ in self.calls]

    def feedback_types(self) -> list[str]:
        return [
            body["event"]["type"] for path, body in self.calls if "feedback" in path
        ]


@pytest.fixture
def fake_client(monkeypatch):
    def install(responses: dict[str, Any]) -> _FakeClient:
        client = _FakeClient(responses)
        monkeypatch.setattr(async_wave, "yandex_token", lambda: "token")
        monkeypatch.setattr(
            async_wave.Clients, "get_yandex_client", lambda self: client
        )
        return client

    return install


@pytest.mark.asyncio
async def test_start_wave_by_mood_opens_session_with_seeds(fake_client) -> None:
    client = fake_client(
        {"/rotor/session/new": _session("S1", "B1", _raw_track("10", 100))}
    )
    service = AsyncWaveService()

    playlist = await service.start_yandex_wave(["mood:calm"])

    assert playlist is not None
    path, body = client.calls[0]
    assert path == "/rotor/session/new"
    assert body["seeds"] == ["mood:calm"]
    assert "queue" not in body
    assert playlist.name == "Сохранять спокойствие"
    assert playlist.seeds == ("mood:calm",)
    assert playlist.session_id == "S1"
    assert [t.track_id for t in playlist.get_tracks()] == ["10"]
    assert client.feedback_types() == ["radioStarted"]
    assert client.paths()[1] == "/rotor/session/S1/feedback/"


@pytest.mark.asyncio
async def test_track_feedback_uses_track_album_id(fake_client) -> None:
    client = fake_client(
        {"/rotor/session/new": _session("S1", "B1", _raw_track("10", 100))}
    )
    service = AsyncWaveService()
    playlist = await service.start_yandex_wave()
    assert playlist is not None

    await service.notify_track_started(playlist.get_current_track(), playlist)

    _, body = client.calls[-1]
    assert body["event"]["type"] == "trackStarted"
    assert body["event"]["trackId"] == "10:100"
    assert body["batchId"] == "B1"


@pytest.mark.asyncio
async def test_skip_vs_finish_and_next_batch(fake_client) -> None:
    client = fake_client(
        {
            "/rotor/session/new": _session(
                "S1", "B1", _raw_track("10", 100), _raw_track("11", 110)
            ),
            "/rotor/session/S1/tracks": _session("S1", "B2", _raw_track("12", 120)),
        }
    )
    service = AsyncWaveService()
    playlist = await service.start_yandex_wave(["activity:run"])
    assert playlist is not None

    first = playlist.get_current_track()
    nxt = await service.continue_after_finish(playlist, first, played_seconds=30.0)
    assert nxt is not None and nxt.track_id == "11"

    last = await service.continue_after_finish(playlist, nxt, played_seconds=200.0)
    assert last is not None and last.track_id == "12"
    await service.drain()  # отчёты Яндексу уходят в фоне, по порядку

    assert client.feedback_types() == [
        "radioStarted",
        "skip",
        "trackStarted",
        "trackFinished",
        "radioStarted",
        "trackStarted",
    ]
    tracks_call = next(b for p, b in client.calls if p.endswith("/tracks"))
    assert tracks_call["queue"] == ["10:100", "11:110"]
    assert playlist.batch_id == "B2"


@pytest.mark.asyncio
async def test_expired_session_reopens_with_same_seeds(fake_client) -> None:
    client = fake_client(
        {
            "/rotor/session/new": _session("S1", "B1", _raw_track("10", 100)),
            "/rotor/session/S1/tracks": RuntimeError("410 Gone"),
        }
    )
    service = AsyncWaveService()
    playlist = await service.start_yandex_wave(["genre:rusrock", "mood:sad"])
    assert playlist is not None
    client.responses["/rotor/session/new"] = _session("S2", "B2", _raw_track("12", 120))

    nxt = await service.continue_after_finish(
        playlist, playlist.get_current_track(), played_seconds=200.0
    )

    assert nxt is not None and nxt.track_id == "12"
    reopen = [b for p, b in client.calls if p == "/rotor/session/new"][-1]
    assert reopen["seeds"] == ["genre:rusrock", "mood:sad"]
    assert reopen["queue"] == ["10:100"]
    assert playlist.session_id == "S2"


@pytest.mark.asyncio
async def test_unknown_session_flag_reopens_session(fake_client) -> None:
    client = fake_client(
        {
            "/rotor/session/new": _session("S1", "B1", _raw_track("10", 100)),
            "/rotor/session/S1/tracks": {"unknownSession": True, "sequence": []},
        }
    )
    service = AsyncWaveService()
    playlist = await service.start_yandex_wave(["mood:calm"])
    assert playlist is not None
    client.responses["/rotor/session/new"] = _session("S2", "B2", _raw_track("12", 120))

    nxt = await service.continue_after_finish(
        playlist, playlist.get_current_track(), played_seconds=200.0
    )

    assert nxt is not None and nxt.track_id == "12"
    assert playlist.session_id == "S2"


@pytest.mark.asyncio
async def test_feedback_follows_cloned_playlist(fake_client) -> None:
    client = fake_client({})
    service = AsyncWaveService()
    clone = WavePlaylist(seeds=("mood:dream",), session_id="S9", batch_id="B9")

    from quantis.models import YandexTrack

    await service.notify_track_started(
        YandexTrack(track_id="5", title="t", author="a"), clone
    )

    path, body = client.calls[-1]
    assert path == "/rotor/session/S9/feedback/"
    assert body["batchId"] == "B9"


@pytest.mark.asyncio
async def test_fetch_wheel_parses_moods_and_skips_promo(fake_client) -> None:
    client = fake_client(
        {
            "/wheel/new": {
                "wheelId": "W",
                "items": [
                    {
                        "id": "diversity:reshuffle",
                        "type": "WAVE",
                        "style": "CONTROL_ACCENT",
                        "data": {
                            "wave": {
                                "name": "Встряхнуть Мою волну",
                                "seeds": ["diversity:reshuffle_1791747184321"],
                            }
                        },
                    },
                    {"id": "download", "type": "PROMO_LINK", "style": "PROMO"},
                    {
                        "id": "mood:calm",
                        "type": "WAVE",
                        "style": "DEFAULT",
                        "data": {
                            "wave": {
                                "name": "Сохранять спокойствие",
                                "description": "Моя волна по настроению",
                                "seeds": ["mood:calm"],
                            },
                            "agent": {
                                "cover": {
                                    "uri": "avatars.mds.yandex.net/get-music-misc/1/img/%%",
                                    "color": "#E7338F",
                                }
                            },
                        },
                    },
                ],
            }
        }
    )

    moods = await AsyncWaveService().fetch_wheel()

    _, body = client.calls[0]
    assert body["context"] == {"type": "WAVE", "data": {"seeds": ["user:onyourwave"]}}
    assert [m.id for m in moods] == ["diversity:reshuffle", "mood:calm"]
    assert moods[0].is_control
    calm = moods[1]
    assert calm == WaveMood(
        id="mood:calm",
        name="Сохранять спокойствие",
        seeds=("mood:calm",),
        description="Моя волна по настроению",
        style="DEFAULT",
        cover_uri="avatars.mds.yandex.net/get-music-misc/1/img/%%",
        color="#E7338F",
    )
    assert (
        calm.cover_url()
        == "https://avatars.mds.yandex.net/get-music-misc/1/img/200x200"
    )


@pytest.mark.asyncio
async def test_no_token_means_no_wave(monkeypatch) -> None:
    monkeypatch.setattr(async_wave, "yandex_token", lambda: None)
    service = AsyncWaveService()
    assert await service.start_yandex_wave(["mood:calm"]) is None
    assert await service.fetch_wheel() == []
