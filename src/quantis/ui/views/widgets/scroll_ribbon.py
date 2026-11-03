"""Горизонтальная лента: края гаснут, стрелки листают на ширину ленты.

Лента шире окна обрезалась посреди элемента, и не было видно, что её можно
листать. Колесо мыши листает вбок, а не страницу.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QResizeEvent, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QWidget,
)

_FADE = 48  # px затухания у края, за которым есть ещё элементы
_ARROW = 28


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


class ScrollRibbon(QWidget):
    """Элементы кладутся в ``row`` (QHBoxLayout, в конце — растяжка)."""

    def __init__(
        self,
        *,
        spacing: int = 8,
        object_name: str = "scrollRibbon",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._arrow_band: int | None = None
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = _HorizontalScroll()
        scroll.setObjectName("ribbonScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        row = QWidget()
        row.setObjectName("ribbonRow")
        self._row = QHBoxLayout(row)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(spacing)
        self._row.addStretch(1)
        scroll.setWidget(row)
        outer.addWidget(scroll)
        self._scroll = scroll

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

    @property
    def row(self) -> QHBoxLayout:
        return self._row

    @property
    def scroll_area(self) -> QScrollArea:
        return self._scroll

    def set_arrow_band(self, height: int | None) -> None:
        """Стрелки по центру верхних ``height`` px (у плейлистов — обложки)."""
        self._arrow_band = height
        self._sync_edges()

    def _make_arrow(self, icon: str, hint: str) -> QToolButton:

        button = QToolButton(self)
        button.setObjectName("ribbonArrow")
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
        band = self._arrow_band if self._arrow_band is not None else self.height()
        y = max(0, (band - _ARROW) // 2)
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
