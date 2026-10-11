"""Лента настроений «Моей волны» — карточки колеса ``/wheel/new``."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from quantis.services.async_wave import WaveMood

_DOT = 10


def _dot_icon(color: str | None) -> QIcon:
    """Цвет карточки из колеса — кружок перед названием."""
    qcolor = QColor(color) if color else QColor()
    if not qcolor.isValid():
        return QIcon()
    pixmap = QPixmap(_DOT * 2, _DOT * 2)
    pixmap.setDevicePixelRatio(2.0)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(qcolor)
    painter.drawEllipse(1, 1, _DOT - 2, _DOT - 2)
    painter.end()
    return QIcon(pixmap)


class _HorizontalScroll(QScrollArea):
    """Колесо мыши листает ленту вбок, а не страницу."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        bar = self.horizontalScrollBar()
        if bar.maximum() <= 0:
            event.ignore()
            return
        delta = event.angleDelta()
        step = delta.x() or delta.y()
        bar.setValue(bar.value() - step)
        event.accept()


class WaveMoodStrip(QWidget):
    """Ряд чипов: настроения, занятия, жанры, артисты, «Встряхнуть»…"""

    mood_activated = Signal(object)
    """WaveMood, по которому включить волну."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("waveMoodStrip")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._moods: tuple[WaveMood, ...] = ()
        self._chips: list[QToolButton] = []

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = _HorizontalScroll()
        scroll.setObjectName("waveMoodScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row = QWidget()
        row.setObjectName("waveMoodRow")
        self._row = QHBoxLayout(row)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(8)
        self._row.addStretch(1)
        scroll.setWidget(row)
        outer.addWidget(scroll)
        self._scroll = scroll

    def moods(self) -> tuple[WaveMood, ...]:
        return self._moods

    def chips(self) -> list[QToolButton]:
        return list(self._chips)

    def set_moods(
        self,
        moods: Sequence[WaveMood],
        *,
        active_seeds: Sequence[str] = (),
        busy: bool = False,
    ) -> None:
        moods = tuple(moods)
        if moods != self._moods:
            self._moods = moods
            self._rebuild()
        active = tuple(active_seeds)
        for chip, mood in zip(self._chips, self._moods, strict=True):
            chip.setChecked(mood.seeds == active and not mood.is_control)
            chip.setEnabled(not busy)
        if self._chips:
            self.setFixedHeight(self._chips[0].sizeHint().height())

    def _rebuild(self) -> None:
        for chip in self._chips:
            self._row.removeWidget(chip)
            chip.deleteLater()
        self._chips = []
        for index, mood in enumerate(self._moods):
            chip = QToolButton()
            chip.setObjectName("waveMoodChip")
            chip.setProperty("control", mood.is_control)
            chip.setText(mood.name)
            chip.setToolTip(mood.description or mood.name)
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            chip.setIcon(_dot_icon(mood.color))
            chip.setIconSize(QSize(_DOT, _DOT))
            # Отметку ставит set_moods, когда волна реально переключилась.
            chip.clicked.connect(
                lambda checked=False, c=chip, m=mood: self._on_clicked(c, m, checked)
            )
            self._row.insertWidget(index, chip)
            self._chips.append(chip)
        self._scroll.horizontalScrollBar().setValue(0)

    def _on_clicked(self, chip: QToolButton, mood: WaveMood, checked: bool) -> None:
        # Клик переключил отметку — возвращаем: отметит set_moods после старта.
        chip.setChecked(not checked)
        self.mood_activated.emit(mood)
