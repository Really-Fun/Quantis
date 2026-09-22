from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame

from quantis.ui.preferences import UiPreferences
from quantis.ui.resources import THEME_EDITORIAL


class GlassPanel(QFrame):
    """Панель контента: QSS для большинства тем, editorial — как «Сейчас играет»."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self._prefs = UiPreferences()
        self._prefs.changed.connect(self._on_theme_changed)
        self._apply_editorial_mode()

    def _on_theme_changed(self) -> None:
        self._apply_editorial_mode()
        self.update()

    def _apply_editorial_mode(self) -> None:
        editorial = self._prefs.ui_theme == THEME_EDITORIAL
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, not editorial)

    def paintEvent(self, event) -> None:
        if self._prefs.ui_theme != THEME_EDITORIAL:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -2, -2)

        painter.fillRect(rect, QColor(12, 12, 14, 200))
        painter.fillRect(rect.left(), rect.top() + 16, 3, 40, QColor(0, 229, 255, 180))
        painter.fillRect(
            rect.left() + 3, rect.top() + 16, 2, 40, QColor(230, 59, 46, 160)
        )
        painter.end()
