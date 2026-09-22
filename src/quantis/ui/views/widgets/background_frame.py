from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget

from quantis.ui.design_tokens import ACCENT_FALLBACK, BG


class BackgroundFrame(QFrame):
    """Каркас окна: Aurora / Glass атмосфера + pulse от динамического акцента."""

    def __init__(
        self,
        wallpaper: str | None = None,
        variant: str = "neon",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("appShell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._variant = variant
        self._phase = 0.0
        self._accent = QColor(ACCENT_FALLBACK)
        _ = wallpaper

        self._content = QWidget(self)
        self._content.setObjectName("appContent")
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._content.setAutoFillBackground(False)
        self._content.setStyleSheet("background: transparent;")

        self._eco = False
        self._cinematic = False
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        # Pulse после первого кадра — не конкурирует с layout/show.
        QTimer.singleShot(400, self._start_pulse_if_needed)

    def _start_pulse_if_needed(self) -> None:
        if self._eco or self._cinematic:
            return
        if self._variant in ("neon", "glass", "yellow_dark", "classic"):
            if not self._timer.isActive():
                self._timer.start()

    def content_host(self) -> QWidget:
        return self._content

    def set_eco(self, enabled: bool) -> None:
        """В фоне останавливаем pulse (~25 fps) — главный GPU-расход UI."""
        if self._eco == enabled:
            return
        self._eco = enabled
        if enabled:
            self._timer.stop()
            self.update()
        elif not self._cinematic and self._variant in (
            "neon",
            "glass",
            "yellow_dark",
            "classic",
        ):
            if not self._timer.isActive():
                self._timer.start()

    def set_cinematic(self, enabled: bool) -> None:
        if self._cinematic == enabled:
            return
        self._cinematic = enabled
        if enabled:
            self._timer.stop()
        else:
            self._start_pulse_if_needed()
        self.update()

    def set_variant(self, variant: str) -> None:
        if self._variant != variant:
            self._variant = variant
            if (
                not self._eco
                and not self._cinematic
                and variant in ("neon", "glass", "yellow_dark", "classic")
            ):
                if not self._timer.isActive():
                    self._timer.start()
            elif variant not in ("neon", "glass", "yellow_dark", "classic"):
                self._timer.stop()
            self.update()

    def set_accent(self, color: QColor) -> None:
        if color.isValid() and color != self._accent:
            self._accent = QColor(color)
            self.update()

    def _tick(self) -> None:
        if self._eco or self._cinematic:
            return
        if self._variant not in ("neon", "glass", "yellow_dark", "classic"):
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

        bases = {
            "light": QColor(250, 251, 252),
            "yellow_dark": QColor(14, 10, 5),
            "editorial": QColor(10, 10, 12),
            "classic": QColor(10, 12, 16),
            "neon": QColor(BG),
            "glass": QColor(11, 13, 18),
        }
        painter.fillRect(rect, bases.get(self._variant, QColor(BG)))

        depth = QLinearGradient(0, 0, 0, h)
        if self._variant == "light":
            depth.setColorAt(0.0, QColor(255, 255, 255, 40))
            depth.setColorAt(1.0, QColor(140, 150, 170, 50))
        elif self._variant == "yellow_dark":
            depth.setColorAt(0.0, QColor(40, 24, 8, 50))
            depth.setColorAt(1.0, QColor(0, 0, 0, 90))
        elif self._variant == "glass":
            depth.setColorAt(0.0, QColor(20, 24, 33, 30))
            depth.setColorAt(1.0, QColor(0, 0, 0, 80))
        else:
            depth.setColorAt(0.0, QColor(20, 28, 48, 40))
            depth.setColorAt(0.55, QColor(0, 0, 0, 0))
            depth.setColorAt(1.0, QColor(0, 0, 0, 110))
        painter.fillRect(rect, depth)

        if self._variant == "editorial":
            painter.end()
            return

        pulse = 0.5 + 0.5 * math.sin(self._phase)
        pulse2 = 0.5 + 0.5 * math.sin(self._phase + 2.1)
        accent = self._accent

        if self._variant in ("neon", "glass"):
            cx = w * (0.78 + 0.06 * math.sin(self._phase * 0.7))
            cy = h * (0.08 + 0.04 * pulse)
            glow = QRadialGradient(cx, cy, w * (0.42 + 0.04 * pulse))
            glow.setColorAt(
                0.0,
                QColor(
                    accent.red(), accent.green(), accent.blue(), int(36 + 16 * pulse)
                ),
            )
            glow.setColorAt(
                0.45,
                QColor(
                    accent.red(), accent.green(), accent.blue(), int(12 + 6 * pulse)
                ),
            )
            glow.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 0))
            painter.fillRect(rect, glow)

            mx = w * (0.12 + 0.05 * math.cos(self._phase * 0.55))
            my = h * (0.85 - 0.05 * pulse2)
            secondary = QColor(
                min(255, accent.red() + 40),
                max(0, accent.green() - 20),
                min(255, accent.blue() + 30),
            )
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

        elif self._variant == "yellow_dark":
            glow = QRadialGradient(w * 0.85, h * 0.05, w * 0.4)
            glow.setColorAt(0.0, QColor(255, 170, 0, int(26 + 10 * pulse)))
            glow.setColorAt(1.0, QColor(255, 170, 0, 0))
            painter.fillRect(rect, glow)
            warm = QRadialGradient(w * 0.15, h * 0.9, w * 0.35)
            warm.setColorAt(0.0, QColor(255, 100, 40, int(18 + 8 * pulse2)))
            warm.setColorAt(1.0, QColor(255, 100, 40, 0))
            painter.fillRect(rect, warm)

        elif self._variant == "classic":
            glow = QRadialGradient(w * 0.7, 0, w * 0.5)
            glow.setColorAt(0.0, QColor(90, 130, 180, int(18 + 8 * pulse)))
            glow.setColorAt(1.0, QColor(90, 130, 180, 0))
            painter.fillRect(rect, glow)

        radius = max(w, h) * 0.78
        vignette = QRadialGradient(rect.center(), radius)
        vignette.setColorAt(0.4, QColor(0, 0, 0, 0))
        if self._variant == "light":
            vignette.setColorAt(1.0, QColor(255, 255, 255, 70))
        else:
            vignette.setColorAt(1.0, QColor(0, 0, 0, 170))
        painter.fillRect(rect, vignette)
        painter.end()
