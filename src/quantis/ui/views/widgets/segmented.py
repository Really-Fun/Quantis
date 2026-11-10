"""Переключатель вкладок-«таблеток»: активная подсвечена акцентом."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from quantis.ui.fonts import app_font
from quantis.ui.views.widgets.delegate_paint_kit import paint_colors

_H = 34
_PAD_X = 16
_GAP = 4


class Segmented(QWidget):
    current_changed = Signal(int)

    def __init__(self, labels: Sequence[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels = list(labels)
        self._current = 0
        self._hover = -1
        self._font = app_font(11, QFont.Weight.DemiBold)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(self.sizeHint())

    @property
    def current(self) -> int:
        return self._current

    def set_current(self, index: int) -> None:
        if 0 <= index < len(self._labels) and index != self._current:
            self._current = index
            self.update()
            self.current_changed.emit(index)

    def _rects(self) -> list[QRectF]:
        metrics = QFontMetrics(self._font)
        rects: list[QRectF] = []
        x = 3.0
        for label in self._labels:
            w = metrics.horizontalAdvance(label) + _PAD_X * 2
            rects.append(QRectF(x, 3, w, _H - 6))
            x += w + _GAP
        return rects

    def sizeHint(self) -> QSize:
        rects = self._rects()
        width = int(rects[-1].right() + 3) if rects else 0
        return QSize(width, _H)

    def _index_at(self, x: float, y: float) -> int:
        for index, rect in enumerate(self._rects()):
            if rect.contains(x, y):
                return index
        return -1

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = self._index_at(event.position().x(), event.position().y())
        if index != self._hover:
            self._hover = index
            self.update()

    def leaveEvent(self, event: object) -> None:
        self._hover = -1
        self.update()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(event.position().x(), event.position().y())
            if index >= 0:
                self.set_current(index)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = paint_colors()
        track = QPainterPath()
        track.addRoundedRect(QRectF(self.rect()), _H / 2, _H / 2)
        painter.fillPath(track, colors.bg_idle)
        painter.setFont(self._font)
        for index, (rect, label) in enumerate(
            zip(self._rects(), self._labels, strict=True)
        ):
            pill = QPainterPath()
            pill.addRoundedRect(rect, rect.height() / 2, rect.height() / 2)
            if index == self._current:
                painter.fillPath(pill, colors.accent)
                painter.setPen(Qt.GlobalColor.white)
            else:
                if index == self._hover:
                    painter.fillPath(pill, colors.bg_hover)
                painter.setPen(
                    colors.subtitle if index != self._hover else colors.title
                )
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.end()
