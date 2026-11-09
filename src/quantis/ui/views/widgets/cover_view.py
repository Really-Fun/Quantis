"""Карточки с картинкой: обложка с закруглёнными углами и адаптивная сетка.

Тот же вид, что у комнат Together: превью 16:9 сверху, пока картинки нет —
градиентная подложка с первой буквой названия.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QResizeEvent,
)
from PySide6.QtWidgets import QGridLayout, QWidget

from quantis.ui.image_fx import fill_crop
from quantis.ui.views.widgets.cover_art import gradient_for_name


class CoverView(QWidget):
    """Картинка как ``object-fit: cover``; без неё — буква на градиенте."""

    def __init__(
        self, label: str, *, radius: int = 12, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._letter = (label.strip()[:1] or "?").upper()
        self._colors = gradient_for_name(label or "?")
        self._radius = radius
        self._image: QImage | None = None
        self._scaled: QImage | None = None

    @property
    def has_image(self) -> bool:
        return self._image is not None

    def set_image(self, image: QImage | None) -> None:
        self._image = image if image is not None and not image.isNull() else None
        self._scaled = None
        self.update()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._scaled = None
        super().resizeEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(path)

        if self._image is not None:
            ratio = self.devicePixelRatioF()
            size = QSize(int(rect.width() * ratio), int(rect.height() * ratio))
            if self._scaled is None or self._scaled.size() != size:
                self._scaled = fill_crop(self._image, size)
                self._scaled.setDevicePixelRatio(ratio)
            painter.drawImage(rect.topLeft(), self._scaled)
            return

        start, end = self._colors
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0.0, QColor(start.red(), start.green(), start.blue(), 150))
        gradient.setColorAt(1.0, QColor(end.red(), end.green(), end.blue(), 90))
        painter.fillPath(path, gradient)
        font = painter.font()
        font.setPixelSize(max(12, int(min(rect.width(), rect.height()) * 0.42)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 215))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._letter)


class CardGrid(QWidget):
    """Сетка карточек: число колонок зависит от ширины."""

    def __init__(
        self,
        min_card_width: int = 240,
        max_columns: int = 4,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._cards: list[QWidget] = []
        self._columns = 0
        self._min_width = min_card_width
        self._max_columns = max_columns
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(14)

    @property
    def cards(self) -> list[QWidget]:
        return list(self._cards)

    def set_cards(self, cards: list[QWidget]) -> None:
        for card in self._cards:
            self._grid.removeWidget(card)
            # Сразу убираем со страницы: deleteLater сработает позже.
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self._cards = list(cards)
        self._columns = 0
        self._relayout()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        columns = max(1, min(self._max_columns, self.width() // self._min_width))
        if columns == self._columns and self._grid.count() == len(self._cards):
            return
        self._columns = columns
        for card in self._cards:
            self._grid.removeWidget(card)
        for index, card in enumerate(self._cards):
            self._grid.addWidget(card, index // columns, index % columns)
        for column in range(self._max_columns):
            self._grid.setColumnStretch(column, 1 if column < columns else 0)
        for row in range(self._grid.rowCount()):
            self._grid.setRowStretch(row, 0)
