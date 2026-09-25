"""Палитра трека в движении: плавный переход между треками для виджетов,
которые рисуют себя сами (фон, сцена, спектр, перемотка).

Кадры перехода идут только через сигнал ``palette_changed`` — никаких stylesheet.
Виджеты со stylesheet получают итоговый акцент один раз через ``AccentStyles``.
"""

from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QEasingCurve, QObject, QTimer, Signal

from quantis.ui.cover_accent import CoverPalette, fallback_palette

TRANSITION_MS = 900
_FRAME_MS = 33  # ~30 к/с: переход медленный, чаще — лишние перерисовки окна


class LivePalette(QObject):
    palette_changed = Signal(object)
    """Текущая палитра (``CoverPalette``): кадр перехода или итог."""

    _instance: LivePalette | None = None

    def __init__(self) -> None:
        super().__init__()
        self._current = fallback_palette()
        self._start = self._current
        self._target = self._current
        self._t0 = 0.0
        self._curve = QEasingCurve(QEasingCurve.Type.InOutCubic)
        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._step)

    @classmethod
    def instance(cls) -> LivePalette:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def current(self) -> CoverPalette:
        return self._current

    @property
    def target(self) -> CoverPalette:
        return self._target

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def set_target(self, palette: CoverPalette, *, animate: bool = True) -> None:
        if palette == self._target and (animate or not self.is_animating()):
            return
        self._target = palette
        if not animate:
            self._timer.stop()
            self._current = palette
            self.palette_changed.emit(palette)
            return
        self._start = self._current
        self._t0 = monotonic()
        if not self._timer.isActive():
            self._timer.start()
        self._step()

    def _step(self) -> None:
        progress = min(1.0, (monotonic() - self._t0) * 1000 / TRANSITION_MS)
        if progress >= 1.0:
            self._timer.stop()
            frame = self._target
        else:
            eased = self._curve.valueForProgress(progress)
            frame = self._start.lerp(self._target, eased)
        if frame == self._current:
            return  # после округления до 8 бит кадр не изменился — не будим окно
        self._current = frame
        self.palette_changed.emit(frame)
