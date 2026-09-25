"""Горизонтальные бары топа прослушиваний."""

from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QSizePolicy, QWidget

from quantis.models import Track
from quantis.ui.design_tokens import ACCENT_FALLBACK
from quantis.ui.preferences import UiPreferences
from quantis.ui.views.widgets.delegate_paint_kit import paint_colors

_ROW_H = 44
_PAD = 4


class ListenBars(QWidget):
    track_activated = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("listenBars")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._tracks: list[Track] = []
        self._hover = -1
        self._accent = QColor(ACCENT_FALLBACK)
        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self.update)
        self.setMouseTracking(True)
        self._sync_height()

    def set_accent(self, color: QColor) -> None:
        if color.isValid():
            self._accent = QColor(color)
            self.update()

    def set_tracks(self, tracks: list[Track]) -> None:
        self._tracks = list(tracks)
        self._hover = -1
        self._sync_height()
        self.update()

    def _sync_height(self) -> None:
        rows = max(1, len(self._tracks))
        self.setFixedHeight(rows * _ROW_H + _PAD * 2)

    def _index_at(self, y: int) -> int:
        if not self._tracks:
            return -1
        row = (y - _PAD) // _ROW_H
        if 0 <= row < len(self._tracks):
            return int(row)
        return -1

    def mouseMoveEvent(self, event) -> None:
        index = self._index_at(int(event.position().y()))
        if index != self._hover:
            self._hover = index
            self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._hover != -1:
            self._hover = -1
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(int(event.position().y()))
            if index >= 0:
                self.track_activated.emit(index)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = paint_colors(self._prefs.ui_theme)
        if not self._tracks:
            painter.setPen(colors.empty)
            painter.setFont(QFont(self.font().family(), 12))
            painter.drawText(
                self.rect().adjusted(12, 0, -12, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                "Пока нет завершённых прослушиваний",
            )
            painter.end()
            return

        peak = max((max(0, t.listen_count) for t in self._tracks), default=1) or 1
        title_font = QFont(self.font().family(), 12)
        title_font.setWeight(QFont.Weight.DemiBold)
        meta_font = QFont(self.font().family(), 10)
        count_font = QFont(self.font().family(), 11)
        count_font.setWeight(QFont.Weight.Bold)

        width = self.width()
        bar_left = 36
        bar_right = width - 72
        bar_span = max(40, bar_right - bar_left)

        for index, track in enumerate(self._tracks):
            y = _PAD + index * _ROW_H
            row = QRect(8, y, width - 16, _ROW_H - 4)
            if index == self._hover:
                hover = QPainterPath()
                hover.addRoundedRect(QRectF(row), 10, 10)
                painter.fillPath(hover, colors.bg_hover)

            painter.setPen(colors.meta)
            painter.setFont(meta_font)
            painter.drawText(
                QRect(12, y, 22, _ROW_H - 4),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(index + 1),
            )

            ratio = max(0.06, min(1.0, track.listen_count / peak))
            bar_w = int(bar_span * ratio)
            bar_rect = QRectF(bar_left, y + 26, bar_w, 8)
            path = QPainterPath()
            path.addRoundedRect(bar_rect, 4, 4)
            gradient = QLinearGradient(bar_rect.topLeft(), bar_rect.topRight())
            accent = self._accent
            gradient.setColorAt(
                0.0,
                QColor(accent.red(), accent.green(), accent.blue(), 220),
            )
            gradient.setColorAt(
                1.0,
                QColor(accent.red(), accent.green(), accent.blue(), 80),
            )
            painter.fillPath(path, gradient)

            painter.setPen(colors.title)
            painter.setFont(title_font)
            painter.drawText(
                QRect(bar_left, y + 2, bar_span, 22),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                painter.fontMetrics().elidedText(
                    track.title or "Без названия",
                    Qt.TextElideMode.ElideRight,
                    bar_span,
                ),
            )

            painter.setPen(colors.subtitle)
            painter.setFont(count_font)
            painter.drawText(
                QRect(bar_right + 8, y, 56, _ROW_H - 4),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                str(track.listen_count),
            )
        painter.end()
