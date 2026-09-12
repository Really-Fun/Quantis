"""Пауза не должна сбрасывать трек в начало."""

from __future__ import annotations

from quantis.models import YandexTrack
from quantis.player.player import Player


class StubEngine:
    def __init__(self) -> None:
        self._playing = False
        self._position = 0
        self._duration = 180_000
        self._volume = 50
        self.seeks: list[int] = []
        self.resume_calls = 0
        self._playing_cbs: list = []
        self._paused_cbs: list = []
        self._stopped_cbs: list = []
        self._ended_cbs: list = []
        self._error_cbs: list = []

    def play_media(self, source: str) -> None:
        self._playing = True
        self._position = 0

    def pause_media(self) -> None:
        self._playing = False

    def resume_media(self) -> None:
        self.resume_calls += 1
        self._playing = True

    def stop_media(self) -> None:
        self._playing = False

    def is_playing(self) -> bool:
        return self._playing

    def get_position_ms(self) -> int:
        return self._position

    def set_position_ms(self, ms: int) -> None:
        self._position = max(0, int(ms))

    def request_seek(self, ms: int) -> None:
        self.seeks.append(ms)
        self._position = max(0, int(ms))

    def get_duration_ms(self) -> int:
        return self._duration

    def get_volume(self) -> int:
        return self._volume

    def set_volume(self, value: int) -> None:
        self._volume = value

    def on_playing(self, callback) -> None:
        self._playing_cbs.append(callback)

    def on_paused(self, callback) -> None:
        self._paused_cbs.append(callback)

    def on_stopped(self, callback) -> None:
        self._stopped_cbs.append(callback)

    def on_ended(self, callback) -> None:
        self._ended_cbs.append(callback)

    def on_error(self, callback) -> None:
        self._error_cbs.append(callback)


def test_pause_resume_seeks_saved_position() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    player.play("/tmp/track.mp3")
    engine._position = 42_000

    player.pause()
    assert player.paused_at_ms == 42_000

    player.resume()
    assert engine.resume_calls == 1
    assert engine.seeks == [42_000]


def test_play_start_ms_requests_seek() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    player.play("/tmp/track.mp3", start_ms=12_000)
    assert engine.seeks == [12_000]


def test_short_http_pause_resumes_in_place() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    errors: list[str] = []
    player.on_stream_error(errors.append)
    player.play("https://cdn.example/a.mp3")
    engine._position = 42_000

    player.pause()
    player.resume()

    assert errors == []
    assert engine.resume_calls == 1
    assert engine.seeks == [42_000]


def test_long_http_pause_refreshes_source() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    errors: list[str] = []
    player.on_stream_error(errors.append)
    player.play("https://cdn.example/a.mp3")
    engine._position = 42_000

    player.pause()
    player._paused_at_mono -= 20.0
    player.resume()

    assert errors == ["resume-after-pause"]
    assert engine.resume_calls == 0


def test_duration_uses_catalog_when_engine_is_short() -> None:
    engine = StubEngine()
    engine._duration = 8_000
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    assert player.duration == 180_000


def test_duration_prefers_longer_engine() -> None:
    engine = StubEngine()
    engine._duration = 200_000
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    assert player.duration == 200_000


def test_duration_ignores_inflated_engine() -> None:
    engine = StubEngine()
    engine._duration = 3_600_000
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    assert player.duration == 180_000


def test_duration_ignores_inflated_catalog_when_engine_is_ready() -> None:
    engine = StubEngine()
    engine._duration = 180_000
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=3_600_000
    )
    assert player.duration == 180_000


def test_is_buffering_without_engine_api() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    assert player.is_buffering() is False


class BufferingStubEngine(StubEngine):
    def is_buffering(self) -> bool:
        return True


def test_is_buffering_uses_engine() -> None:
    player = Player(engine=BufferingStubEngine())
    assert player.is_buffering() is True


def _start(player: Player, engine: StubEngine, source: str) -> None:
    player.play(source)
    for callback in list(engine._playing_cbs):
        callback()


def test_local_early_end_requests_recovery() -> None:
    engine = StubEngine()
    engine._duration = 20_000
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    errors: list[str] = []
    finished: list[int] = []
    player.on_stream_error(errors.append)
    player.on_track_finished(lambda: finished.append(1))
    _start(player, engine, "/tmp/quantis_stream/yandex_1.mp3")
    engine._position = 20_000

    for callback in list(engine._ended_cbs):
        callback()

    assert errors == ["ended-early"]
    assert finished == []


def test_http_preview_still_finishes() -> None:
    engine = StubEngine()
    engine._duration = 30_000
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    errors: list[str] = []
    finished: list[int] = []
    player.on_stream_error(errors.append)
    player.on_track_finished(lambda: finished.append(1))
    _start(player, engine, "https://cdn.example/preview.mp3")
    engine._position = 30_000

    for callback in list(engine._ended_cbs):
        callback()

    assert errors == []
    assert finished == [1]


def test_end_of_media_at_start_recovers_instead_of_skipping() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    errors: list[str] = []
    finished: list[int] = []
    player.on_stream_error(errors.append)
    player.on_track_finished(lambda: finished.append(1))
    _start(player, engine, "https://cdn.example/full.mp3")
    engine._position = 400

    for callback in list(engine._ended_cbs):
        callback()

    assert errors == ["ended-early"]
    assert finished == []


def test_end_of_media_before_playing_is_ignored() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    errors: list[str] = []
    finished: list[int] = []
    player.on_stream_error(errors.append)
    player.on_track_finished(lambda: finished.append(1))
    player.play("https://cdn.example/full.mp3")

    for callback in list(engine._ended_cbs):
        callback()

    assert errors == []
    assert finished == []


def test_end_of_media_with_reset_position_finishes() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    errors: list[str] = []
    finished: list[int] = []
    player.on_stream_error(errors.append)
    player.on_track_finished(lambda: finished.append(1))
    _start(player, engine, "https://cdn.example/full.mp3")
    engine._position = 179_000
    assert player.time == 179_000
    engine._position = 0

    for callback in list(engine._ended_cbs):
        callback()

    assert errors == []
    assert finished == [1]


def test_notify_natural_end_finishes_once() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    player.current_track = YandexTrack(
        track_id="1", title="T", author="A", duration_ms=180_000
    )
    finished: list[int] = []
    player.on_track_finished(lambda: finished.append(1))
    _start(player, engine, "https://cdn.example/full.mp3")
    engine._position = 179_800
    player.notify_natural_end()
    player.notify_natural_end()
    assert finished == [1]


def test_http_pause_reset_to_zero_refreshes_source() -> None:
    engine = StubEngine()
    player = Player(engine=engine)
    errors: list[str] = []
    player.on_stream_error(errors.append)
    player.play("https://cdn.example/a.mp3")
    engine._position = 42_000

    player.pause()
    engine._position = 0
    player.resume()

    assert errors == ["resume-after-pause"]
    assert engine.resume_calls == 0
    assert player.paused_at_ms == 42_000
