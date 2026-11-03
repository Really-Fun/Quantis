"""Лента настроений «Моей волны» — карточки колеса ``/wheel/new``."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QLinearGradient,
    QPainter,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from quantis.services.async_wave import WaveMood

_DOT = 10
_FADE = 48  # px затухания у края, за которым есть ещё чипы
_ARROW = 28


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

        # Лента шире окна обрезалась посреди слова, и не было видно, что её
        # можно листать: края гаснут, а стрелки листают на ширину ленты.
        self._fade = QGraphicsOpacityEffect(scroll)
        scroll.setGraphicsEffect(self._fade)
        self._back_btn = self._make_arrow("chevron-left.svg", "Назад по ленте")
        self._back_btn.clicked.connect(self.scroll_back)
        self._forward_btn = self._make_arrow("chevron-right.svg", "Дальше по ленте")
        self._forward_btn.clicked.connect(self.scroll_forward)
        from quantis.ui.preferences import UiPreferences

        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self._tint_arrows)
        self._tint_arrows()
        bar = scroll.horizontalScrollBar()
        bar.valueChanged.connect(self._sync_edges)
        bar.rangeChanged.connect(self._sync_edges)
        self._sync_edges()

    def _make_arrow(self, icon: str, hint: str) -> QToolButton:

        button = QToolButton(self)
        button.setObjectName("waveMoodArrow")
        button.setProperty("iconName", icon)
        button.setIconSize(QSize(14, 14))
        button.setToolTip(hint)
        button.setAccessibleName(hint)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(_ARROW, _ARROW)
        button.hide()
        return button

    def _tint_arrows(self) -> None:
        from quantis.ui import resources
        from quantis.ui.themes.spec import qcolor

        color = qcolor(self._prefs.theme.colors.ink_rgb)
        for button in (self._back_btn, self._forward_btn):
            button.setIcon(resources.load_icon(button.property("iconName"), color))

    @property
    def can_scroll_back(self) -> bool:
        return self._scroll.horizontalScrollBar().value() > 0

    @property
    def can_scroll_forward(self) -> bool:
        bar = self._scroll.horizontalScrollBar()
        return bar.value() < bar.maximum()

    def scroll_back(self) -> None:
        self._page(-1)

    def scroll_forward(self) -> None:
        self._page(1)

    def _page(self, direction: int) -> None:
        bar = self._scroll.horizontalScrollBar()
        step = max(1, int(self._scroll.viewport().width() * 0.8))
        bar.setValue(bar.value() + direction * step)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_edges()

    def _sync_edges(self, *_: object) -> None:
        back, forward = self.can_scroll_back, self.can_scroll_forward
        y = max(0, (self.height() - _ARROW) // 2)
        self._back_btn.move(0, y)
        self._forward_btn.move(self.width() - _ARROW, y)
        self._back_btn.setVisible(back)
        self._forward_btn.setVisible(forward)
        self._back_btn.raise_()
        self._forward_btn.raise_()
        width = max(1, self._scroll.width())
        fade = min(0.45, _FADE / width)
        mask = QLinearGradient(QPointF(0, 0), QPointF(width, 0))
        mask.setColorAt(0, QColor(0, 0, 0, 0 if back else 255))
        mask.setColorAt(fade, QColor(0, 0, 0, 255))
        mask.setColorAt(1 - fade, QColor(0, 0, 0, 255))
        mask.setColorAt(1, QColor(0, 0, 0, 0 if forward else 255))
        self._fade.setOpacityMask(QBrush(mask))
        self._fade.setEnabled(back or forward)

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
        self._sync_edges()

    def _on_clicked(self, chip: QToolButton, mood: WaveMood, checked: bool) -> None:
        # Клик переключил отметку — возвращаем: отметит set_moods после старта.
        chip.setChecked(not checked)
        self.mood_activated.emit(mood)
