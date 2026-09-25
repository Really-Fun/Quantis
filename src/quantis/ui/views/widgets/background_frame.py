from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget

from quantis.ui.cover_accent import CoverPalette, fallback_palette
from quantis.ui.themes import registry
from quantis.ui.themes.spec import GlowSpec, ThemeSpec, qcolor


class BackgroundFrame(QFrame):
    """Каркас окна: фон темы (ThemeSpec.backdrop) + свечение, дышащее по таймеру."""

    def __init__(
        self,
        wallpaper: str | None = None,
        theme: ThemeSpec | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("appShell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._theme = theme or registry.default()
        self._phase = 0.0
        self._palette = fallback_palette(self._theme)
        _ = wallpaper

        self._content = QWidget(self)
        self._content.setObjectName("appContent")
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._content.setAutoFillBackground(False)
        self._content.setStyleSheet("#appContent { background: transparent; }")

        self._eco = False
        self._cinematic = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        # Pulse после первого кадра — не конкурирует с layout/show.
        QTimer.singleShot(400, self._sync_timer)

    def _animated(self) -> bool:
        return self._theme.backdrop.glow is not None

    def _sync_timer(self) -> None:
        if self._animated() and not self._eco and not self._cinematic:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def content_host(self) -> QWidget:
        return self._content

    def set_eco(self, enabled: bool) -> None:
        """В фоне останавливаем pulse (~25 fps) — главный GPU-расход UI."""
        if self._eco == enabled:
            return
        self._eco = enabled
        self._sync_timer()
        if enabled:
            self.update()

    def set_cinematic(self, enabled: bool) -> None:
        if self._cinematic == enabled:
            return
        self._cinematic = enabled
        self._sync_timer()
        self.update()

    def set_theme(self, theme: ThemeSpec) -> None:
        if self._theme is not theme:
            self._theme = theme
            self._sync_timer()
            self.update()

    def set_palette(self, palette: CoverPalette) -> None:
        """Палитра трека (и кадры перехода между треками)."""
        if palette != self._palette:
            self._palette = palette
            if self._theme.backdrop.glow is not None and (
                self._theme.backdrop.glow.style == "cover"
            ):
                self.update()

    def _tick(self) -> None:
        if self._eco or self._cinematic or not self._animated():
            return
        self._phase = (self._phase + 0.012) % (math.tau)
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._content.setGeometry(self.rect())

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if self._cinematic:
            painter.fillRect(rect, QColor(0, 0, 0))
            painter.end()
            return
        w, h = rect.width(), rect.height()
        backdrop = self._theme.backdrop

        painter.fillRect(rect, qcolor(self._theme.colors.bg))
        depth = QLinearGradient(0, 0, 0, h)
        for pos, color in backdrop.depth:
            depth.setColorAt(pos, qcolor(color))
        painter.fillRect(rect, depth)

        glow = backdrop.glow
        if glow is not None:
            if glow.style == "cover":
                self._paint_cover_glow(painter, w, h)
            else:
                self._paint_spots(painter, w, h, glow)

        if backdrop.vignette is not None:
            vignette = QRadialGradient(rect.center(), max(w, h) * 0.78)
            vignette.setColorAt(0.4, QColor(0, 0, 0, 0))
            vignette.setColorAt(1.0, qcolor(backdrop.vignette))
            painter.fillRect(rect, vignette)
        painter.end()

    def _paint_spots(self, painter: QPainter, w: int, h: int, glow: GlowSpec) -> None:
        for spot in glow.spots:
            pulse = 0.5 + 0.5 * math.sin(self._phase + spot.phase)
            color = qcolor(spot.rgb)
            gradient = QRadialGradient(w * spot.x, h * spot.y, w * spot.radius)
            color.setAlpha(int(spot.alpha + spot.pulse_alpha * pulse))
            gradient.setColorAt(0.0, color)
            color.setAlpha(0)
            gradient.setColorAt(1.0, color)
            painter.fillRect(self.rect(), gradient)

    def _paint_cover_glow(self, painter: QPainter, w: int, h: int) -> None:
        """Два пятна цвета обложки медленно плывут по окну."""
        rect = self.rect()
        pulse = 0.5 + 0.5 * math.sin(self._phase)
        pulse2 = 0.5 + 0.5 * math.sin(self._phase + 2.1)
        accent = self._palette.accent

        cx = w * (0.78 + 0.06 * math.sin(self._phase * 0.7))
        cy = h * (0.08 + 0.04 * pulse)
        glow = QRadialGradient(cx, cy, w * (0.42 + 0.04 * pulse))
        glow.setColorAt(
            0.0,
            QColor(accent.red(), accent.green(), accent.blue(), int(36 + 16 * pulse)),
        )
        glow.setColorAt(
            0.45,
            QColor(accent.red(), accent.green(), accent.blue(), int(12 + 6 * pulse)),
        )
        glow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
        painter.fillRect(rect, glow)

        mx = w * (0.12 + 0.05 * math.cos(self._phase * 0.55))
        my = h * (0.85 - 0.05 * pulse2)
        secondary = self._palette.accent2
        coral = QRadialGradient(mx, my, w * (0.38 + 0.05 * pulse2))
        coral.setColorAt(
            0.0,
            QColor(
                secondary.red(),
                secondary.green(),
                secondary.blue(),
                int(24 + 10 * pulse2),
            ),
        )
        coral.setColorAt(
            0.5, QColor(secondary.red(), secondary.green(), secondary.blue(), 8)
        )
        coral.setColorAt(
            1.0, QColor(secondary.red(), secondary.green(), secondary.blue(), 0)
        )
        painter.fillRect(rect, coral)
