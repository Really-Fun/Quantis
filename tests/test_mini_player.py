from __future__ import annotations

from PySide6.QtCore import QObject, QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent

from quantis.models.track import Track
from quantis.ui.views.widgets import mini_player
from quantis.ui.views.widgets.mini_player import (
    BASELINE,
    PAD,
    WIDTH,
    MiniPlayer,
    wave_heights,
)


class _FakeVm(QObject):
    track_changed = Signal(object)
    is_playing_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[object] = []

    def toggle_pause(self) -> None:
        self.calls.append("toggle")

    def play_next(self) -> None:
        self.calls.append("next")

    def play_previous(self) -> None:
        self.calls.append("prev")

    def seek(self, position_ms: int) -> None:
        self.calls.append(("seek", position_ms))

    def nudge_volume(self, delta: int) -> None:
        self.calls.append(("volume", delta))

    def sync_from_player(self) -> None:
        self.calls.append("sync")


class _Paths:
    def get_cover_path(self, track: Track) -> str:
        return "/nonexistent/cover.jpg"


def _mini(qapp) -> tuple[MiniPlayer, _FakeVm]:
    vm = _FakeVm()
    return MiniPlayer(vm, _Paths()), vm  # type: ignore[arg-type]


def _mouse(kind, x: float, y: float) -> QMouseEvent:
    return QMouseEvent(
        kind,
        QPointF(x, y),
        QPointF(x, y),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


def test_wave_is_bounded_calm_on_pause_and_differs_per_track() -> None:
    loud = wave_heights("a", 1.0, 1.0)
    assert all(0.0 <= h <= 1.0 for h in loud) and max(loud) > 0.2
    assert loud[0] == 0.0 and loud[-1] < 0.01  # края прижаты к линии
    assert max(wave_heights("a", 1.0, 0.0)) == 0.0
    assert wave_heights("b", 1.0, 1.0) != loud
    assert wave_heights("a", 2.0, 1.0) != loud  # волна движется


def test_buttons_and_keys_drive_the_player(qapp) -> None:
    mini, vm = _mini(qapp)
    restored: list[bool] = []
    mini.restore_requested.connect(lambda: restored.append(True))
    mini._play.click()
    mini._next.click()
    mini._prev.click()
    mini._restore.click()
    assert vm.calls == ["toggle", "next", "prev"] and restored == [True]
    mini.sync()
    assert vm.calls[-1] == "sync"


def test_click_on_wave_seeks(qapp) -> None:
    from PySide6.QtCore import QEvent

    mini, vm = _mini(qapp)
    vm.duration_changed.emit(200_000)
    x = PAD + (WIDTH - 2 * PAD) / 2
    mini.mousePressEvent(_mouse(QEvent.Type.MouseButtonPress, x, BASELINE - 5))
    assert mini._shown_position() == 100_000  # пока тянут — показываем цель
    mini.mouseReleaseEvent(_mouse(QEvent.Type.MouseButtonRelease, x, BASELINE - 5))
    assert vm.calls == [("seek", 100_000)]


def test_position_keeps_moving_between_rare_updates(qapp, monkeypatch) -> None:
    mini, vm = _mini(qapp)
    now = [100.0]
    monkeypatch.setattr(mini_player, "monotonic", lambda: now[0])
    vm.duration_changed.emit(200_000)
    vm.is_playing_changed.emit(True)
    vm.position_changed.emit(10_000)
    now[0] += 1.5
    assert mini._shown_position() == 11_500
    now[0] += 60  # плеер молчит слишком долго — дальше 3 с не убегаем
    assert mini._shown_position() == 13_000
    vm.is_playing_changed.emit(False)
    now[0] += 5
    assert mini._shown_position() == 13_000  # на паузе стоит


def test_animation_runs_only_while_visible_and_playing(qapp) -> None:
    mini, vm = _mini(qapp)
    vm.track_changed.emit(Track(1, "Song", "Artist"))
    vm.is_playing_changed.emit(True)
    assert not mini._timer.isActive()  # окно не показано
    mini.show()
    assert mini._timer.isActive()
    assert not mini.grab().isNull()
    vm.is_playing_changed.emit(False)
    for _ in range(80):  # волна затихает и таймер встаёт
        mini._tick()
    assert not mini._timer.isActive() and mini._level == 0.0
    mini.close()


def test_mini_player_is_off_until_enabled_in_settings(qapp) -> None:
    from quantis.ui.preferences import UiPreferences

    prefs = UiPreferences()
    prefs.set_mini_player_enabled(False)
    assert prefs.mini_player_enabled is False
    heard: list[bool] = []
    prefs.layout_changed.connect(lambda: heard.append(prefs.mini_player_enabled))
    try:
        prefs.set_mini_player_enabled(True)
        assert heard == [True]
    finally:
        prefs.set_mini_player_enabled(False)
