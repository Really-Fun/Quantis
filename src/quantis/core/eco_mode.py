"""Экономный режим: меньше CPU/GPU/сети, пока окно в фоне (игры)."""

from __future__ import annotations

import logging
import sys
from typing import Callable

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)

_NORMAL = 0x00000020
_BELOW_NORMAL = 0x00004000


def _set_process_priority(below_normal: bool) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        handle = ctypes.windll.kernel32.GetCurrentProcess()
        cls = _BELOW_NORMAL if below_normal else _NORMAL
        if not ctypes.windll.kernel32.SetPriorityClass(handle, cls):
            logger.debug("SetPriorityClass failed")
    except Exception:
        logger.debug("Не удалось сменить приоритет процесса", exc_info=True)


class EcoMode(QObject):
    """Единый флаг: окно в фоне / принудительный эконом из настроек."""

    changed = Signal(bool)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._window_background = False
        self._pref_enabled = True
        self._active = False
        self._listeners: list[Callable[[bool], None]] = []

    @property
    def active(self) -> bool:
        return self._active

    def set_pref_enabled(self, enabled: bool) -> None:
        self._pref_enabled = enabled
        self._recompute()

    def set_window_background(self, background: bool) -> None:
        self._window_background = background
        self._recompute()

    def subscribe(self, callback: Callable[[bool], None]) -> None:
        self._listeners.append(callback)
        callback(self._active)

    def _recompute(self) -> None:
        active = bool(self._pref_enabled and self._window_background)
        if active == self._active:
            return
        self._active = active
        _set_process_priority(active)
        logger.info("Eco mode %s", "ON" if active else "OFF")
        self.changed.emit(active)
        for callback in self._listeners:
            try:
                callback(active)
            except Exception:
                logger.exception("Eco listener error")
