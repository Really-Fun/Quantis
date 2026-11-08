"""Переключатель «вкл/выкл» цветами темы."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QWidget

from quantis.ui.corners import corner
from quantis.ui.themes.spec import ThemeSpec, qcolor


class Switch(QAbstractButton):
    """Дорожка ``tint`` (включено) или чернила темы, ручка ``handle``.

    ``theme`` — откуда брать тему при отрисовке: панель фона показывает
    тему своего компоновщика, остальные — тему из настроек.
    """

    def __init__(
        self,
        theme: Callable[[], ThemeSpec] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if theme is None:
            from quantis.ui.preferences import UiPreferences

            prefs = UiPreferences()
            prefs.theme_changed.connect(self.update)
            theme = lambda: prefs.theme  # noqa: E731
        self._theme = theme
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # пробел переключает
        self.setFixedSize(40, 24)

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = self._theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            painter.setOpacity(0.4)
        track = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.isChecked():
            painter.setBrush(qcolor(theme.colors.tint))
        else:
            ink = qcolor(theme.colors.ink_rgb)
            ink.setAlpha(46)
            painter.setBrush(ink)
        painter.drawRoundedRect(
            track, corner(track.height() / 2), corner(track.height() / 2)
        )
        if self.hasFocus():
            ring = qcolor(theme.colors.tint)
            painter.setPen(ring)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                track.adjusted(-0.5, -0.5, 0.5, 0.5),
                corner(track.height() / 2),
                corner(track.height() / 2),
            )
            painter.setPen(Qt.PenStyle.NoPen)
        knob = track.height() - 6
        x = track.right() - knob - 3 if self.isChecked() else track.left() + 3
        painter.setBrush(qcolor(theme.colors.handle))
        painter.drawEllipse(QRectF(x, track.top() + 3, knob, knob))
        painter.end()
