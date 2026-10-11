"""429 «Concurrency limit exceeded» от Яндекса: повтор и бережная предзагрузка."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.controllers.playback_controller import PlaybackController
from quantis.models import YandexTrack
from quantis.services import yandex_streamer
from quantis.services.yandex_streamer import AsyncYandexStreamer


def _track() -> YandexTrack:
    return YandexTrack(track_id="1", title="Song", author="A")


def test_stream_url_retries_after_rate_limit(monkeypatch) -> None:
    streamer = AsyncYandexStreamer(executor=None)  # type: ignore[arg-type]
    monkeypatch.setattr(streamer, "_yandex_token", lambda: "token")
    monkeypatch.setattr(yandex_streamer.time, "sleep", lambda _s: None)
    answers = iter(
        [
            RuntimeError("Unknown HTTPError (429): b'Concurrency limit exceeded'"),
            RuntimeError("Unknown HTTPError (429): b'Concurrency limit exceeded'"),
            "https://cdn/ok.mp3",
        ]
    )

    def fetch(_track, _token):
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(streamer, "_fetch_stream_url", fetch)
    assert streamer._sync_get_stream_url(_track()) == "https://cdn/ok.mp3"


def test_stream_url_does_not_retry_other_errors(monkeypatch) -> None:
    streamer = AsyncYandexStreamer(executor=None)  # type: ignore[arg-type]
    monkeypatch.setattr(streamer, "_yandex_token", lambda: "token")
    calls: list[int] = []

    def fetch(_track, _token):
        calls.append(1)
        raise RuntimeError("404 not found")

    monkeypatch.setattr(streamer, "_fetch_stream_url", fetch)
    assert streamer._sync_get_stream_url(_track()) is None
    assert calls == [1]


def _controller(duration_ms: int, time_ms: int) -> PlaybackController:
    player = MagicMock()
    player.duration = duration_ms
    player.time = time_ms
    return PlaybackController(
        player=player,
        playlist_manager=MagicMock(),
        music_service=MagicMock(),
        event_bus=None,
        async_bridge=None,
    )


def test_prefetch_waits_until_near_track_end() -> None:
    controller = _controller(duration_ms=200_000, time_ms=5_000)
    assert controller._prefetch_delay_s(_track()) == pytest.approx(160.0)
    near_end = _controller(duration_ms=200_000, time_ms=180_000)
    assert near_end._prefetch_delay_s(_track()) == 0.0


@pytest.mark.asyncio
async def test_prefetch_skipped_when_track_changed(monkeypatch) -> None:
    controller = _controller(duration_ms=60_000, time_ms=0)
    first, second = _track(), YandexTrack(track_id="2", title="B", author="A")
    playlist = MagicMock()
    playlist.__len__.return_value = 2
    playlist.tracks.values = (first, second)
    controller.playlist_manager.current_playlist = playlist
    controller.music.streamer.prefetch_stream = AsyncMock()

    async def fake_sleep(_seconds: float) -> None:
        controller._play_seq += 1  # пока ждали, пользователь включил другое

    monkeypatch.setattr(
        "quantis.controllers.playback_controller.asyncio.sleep", fake_sleep
    )
    await controller._prefetch_next_track(first)
    controller.music.streamer.prefetch_stream.assert_not_awaited()
