from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class BaseViewModel(QObject):
    loading_changed = Signal(bool)
    error_occurred = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._loading = False

    @property
    def loading(self) -> bool:
        return self._loading

    def set_loading(self, value: bool) -> None:
        if self._loading != value:
            self._loading = value
            self.loading_changed.emit(value)

    def emit_error(self, message: str) -> None:
        self.error_occurred.emit(message)
