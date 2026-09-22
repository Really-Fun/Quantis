"""Duck-gain не меняет пользовательскую громкость."""

from __future__ import annotations

from quantis.player.engine import QtMediaEngine
from quantis.player.player import Player


class _DuckEngine:
    def __init__(self) -> None:
        self._volume = 80
        self._duck = 1.0
        self.output = 80
        self._playing_cbs: list = []
        self._paused_cbs: list = []
        self._stopped_cbs: list = []
        self._ended_cbs: list = []
        self._error_cbs: list = []

    def play_media(self, source: str) -> None:
        return None

    def pause_media(self) -> None:
        return None

    def resume_media(self) -> None:
        return None

    def stop_media(self) -> None:
        return None

    def is_playing(self) -> bool:
        return False

    def get_position_ms(self) -> int:
        return 0

    def set_position_ms(self, ms: int) -> None:
        return None

    def request_seek(self, ms: int) -> None:
        return None

    def get_duration_ms(self) -> int:
        return 0

    def get_volume(self) -> int:
        return self._volume

    def set_volume(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))
        self._apply()

    def get_duck_gain(self) -> float:
        return self._duck

    def set_duck_gain(self, gain: float) -> None:
        self._duck = max(0.0, min(1.0, float(gain)))
        self._apply()

    def _apply(self) -> None:
        self.output = max(0, min(100, int(round(self._volume * self._duck))))

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


def test_player_duck_gain_keeps_user_volume() -> None:
    engine = _DuckEngine()
    player = Player(engine=engine)
    player.volume = 80
    player.set_duck_gain(0.25)
    assert player.volume == 80
    assert abs(player.duck_gain() - 0.25) < 1e-6
    assert engine.output == 20
    player.volume = 100
    assert player.volume == 100
    assert engine.output == 25


def test_player_duck_gain_without_engine_api() -> None:
    class BareEngine:
        def play_media(self, source: str) -> None:
            return None

        def pause_media(self) -> None:
            return None

        def resume_media(self) -> None:
            return None

        def stop_media(self) -> None:
            return None

        def is_playing(self) -> bool:
            return False

        def get_position_ms(self) -> int:
            return 0

        def set_position_ms(self, ms: int) -> None:
            return None

        def get_duration_ms(self) -> int:
            return 0

        def get_volume(self) -> int:
            return 50

        def set_volume(self, value: int) -> None:
            return None

        def on_playing(self, callback) -> None:
            return None

        def on_paused(self, callback) -> None:
            return None

        def on_stopped(self, callback) -> None:
            return None

        def on_ended(self, callback) -> None:
            return None

        def on_error(self, callback) -> None:
            return None

    player = Player(engine=BareEngine())  # type: ignore[arg-type]
    player.set_duck_gain(0.3)
    assert player.duck_gain() == 1.0


def test_qt_duck_gain_does_not_change_reported_volume(qapp) -> None:
    from quantis.player.volume import output_gain

    engine = QtMediaEngine()
    engine.set_volume(80)
    engine.set_duck_gain(0.5)
    assert engine.get_volume() == 80
    assert abs(engine.audio_output.volume() - output_gain(80, 0.5)) < 0.02
    engine.set_volume(100)
    assert engine.get_volume() == 100
    assert abs(engine.audio_output.volume() - 0.5) < 0.02
    engine.set_duck_gain(1.0)
    assert engine.get_volume() == 100
    assert abs(engine.audio_output.volume() - 1.0) < 0.02
