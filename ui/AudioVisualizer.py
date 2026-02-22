"""Виджет-визуализатор аудио (неоновая волна с отражением и свечением).

Зависит только от VizualPlayer (FFT-данные), не от Player.
Single Responsibility: отрисовка спектра.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import (
    QColor, QPainter, QPen, QPainterPath,
    QLinearGradient, QBrush,
)
from PySide6.QtWidgets import QWidget

from player.visualizer import VizualPlayer
from ui.theme import (
    ACCENT,
    ACCENT_DIM,
    AMPLITUDE,
    DECAY,
    FREQ_MAX,
    FREQ_MIN,
    GAIN,
    GLOW_LAYERS,
    MID_RATIO,
    MIN_BARS,
    REFRESH_MS_DEFAULT,
    REFRESH_MS_MAX,
    REFRESH_MS_MIN,
    SMOOTHING,
)


def _build_smooth_path(points: list[QPointF]) -> QPainterPath:
    """Catmull-Rom -> cubic Bezier для идеально гладкой кривой."""
    path = QPainterPath()
    n = len(points)
    if n < 2:
        return path

    path.moveTo(points[0])

    if n == 2:
        path.lineTo(points[1])
        return path

    for i in range(n - 1):
        p0 = points[max(i - 1, 0)]
        p1 = points[i]
        p2 = points[min(i + 1, n - 1)]
        p3 = points[min(i + 2, n - 1)]

        t = SMOOTHING
        cp1 = QPointF(
            p1.x() + (p2.x() - p0.x()) * t,
            p1.y() + (p2.y() - p0.y()) * t,
        )
        cp2 = QPointF(
            p2.x() - (p3.x() - p1.x()) * t,
            p2.y() - (p3.y() - p1.y()) * t,
        )
        path.cubicTo(cp1, cp2, p2)

    return path


def _build_sharp_path(points: list[QPointF]) -> QPainterPath:
    """Строит ломаную линию без сглаживания."""
    path = QPainterPath()
    if len(points) < 2:
        return path
    path.moveTo(points[0])
    for pt in points[1:]:
        path.lineTo(pt)
    return path


def _build_choppy_path(points: list[QPointF], mid: float) -> QPainterPath:
    """Строит разрывистую/ступенчатую линию."""
    path = QPainterPath()
    if len(points) < 2:
        return path
    path.moveTo(points[0])
    for i, pt in enumerate(points[1:], start=1):
        if i % 3 == 0:
            path.lineTo(QPointF(pt.x(), mid))
        path.lineTo(pt)
    return path


class AudioVisualizer(QWidget):
    """Неоновая волна с glow-эффектом и зеркальным отражением."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        bar_count: int = 64,
        height: int = 120,
        delay_ms: int = REFRESH_MS_DEFAULT,
        color_rgb: tuple[int, int, int] = (0, 220, 255),
        mode: str = "smooth",
    ) -> None:
        super().__init__(parent)

        self._bar_count = max(MIN_BARS, int(bar_count))
        self._levels: list[float] = [0.0] * self._bar_count
        self._mode = "smooth"
        self._delay_ms = REFRESH_MS_DEFAULT
        self._color = QColor(*color_rgb)

        self.setFixedHeight(int(height))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._viz = VizualPlayer()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self.set_delay_ms(delay_ms)
        self.set_mode(mode)

    def set_delay_ms(self, delay_ms: int) -> None:
        """Обновляет частоту обновления визуализатора."""
        self._delay_ms = max(REFRESH_MS_MIN, min(REFRESH_MS_MAX, int(delay_ms)))
        self._timer.start(self._delay_ms)

    def set_color_rgb(self, color_rgb: tuple[int, int, int]) -> None:
        """Обновляет цвет визуализатора (R, G, B)."""
        r, g, b = color_rgb
        self._color = QColor(max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))

    def set_mode(self, mode: str) -> None:
        """Устанавливает режим визуализатора: smooth/sharp/choppy."""
        mode_value = str(mode).strip().lower()
        if mode_value not in {"smooth", "sharp", "choppy"}:
            mode_value = "smooth"
        self._mode = mode_value

    # --- FFT -> levels ---

    def _update_levels(self) -> None:
        targets = self._raw_levels()
        for i in range(self._bar_count):
            target = max(0.0, min(1.0, targets[i]))
            self._levels[i] = max(target, self._levels[i] * DECAY)

    def _raw_levels(self) -> list[float]:
        res = self._viz.get_fft()
        if res is None:
            return [0.0] * self._bar_count

        freqs, mags = res
        if mags.size == 0:
            return [0.0] * self._bar_count

        mask = (freqs >= FREQ_MIN) & (freqs <= FREQ_MAX)
        mags = mags[mask]
        if mags.size == 0:
            return [0.0] * self._bar_count

        chunks = np.array_split(mags, self._bar_count)
        return [float(c.mean()) if c.size else 0.0 for c in chunks]

    # --- Points ---

    def _make_points(self, w: int, mid: float, amplitude: float, flip: bool = False) -> list[QPointF]:
        step = w / max(1, self._bar_count - 1)
        sign = 1.0 if not flip else -1.0
        pts: list[QPointF] = []
        for i, level in enumerate(self._levels):
            x = i * step
            boosted = min(1.0, level * GAIN)
            y = mid - sign * boosted * amplitude
            pts.append(QPointF(x, y))
        return pts

    # --- Paint ---

    def paintEvent(self, event) -> None:
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        self._update_levels()

        mid = h * MID_RATIO
        amplitude = h * AMPLITUDE

        top_pts = self._make_points(w, mid, amplitude, flip=False)
        bot_pts = self._make_points(w, mid, amplitude, flip=True)

        if self._mode == "sharp":
            top_path = _build_sharp_path(top_pts)
            bot_path = _build_sharp_path(bot_pts)
        elif self._mode == "choppy":
            top_path = _build_choppy_path(top_pts, mid)
            bot_path = _build_choppy_path(bot_pts, mid)
        else:
            top_path = _build_smooth_path(top_pts)
            bot_path = _build_smooth_path(bot_pts)

        # Fill gradient (subtle area under/over curve)
        fill_color_top = QColor(self._color.red(), self._color.green(), self._color.blue(), 25)
        fill_color_mid = QColor(self._color.red(), self._color.green(), self._color.blue(), 0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        # --- filled area (top wave) ---
        fill_top = QPainterPath(top_path)
        fill_top.lineTo(w, mid)
        fill_top.lineTo(0, mid)
        fill_top.closeSubpath()

        grad_top = QLinearGradient(0, 0, 0, mid)
        grad_top.setColorAt(0.0, fill_color_top)
        grad_top.setColorAt(1.0, fill_color_mid)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad_top))
        painter.drawPath(fill_top)

        # --- filled area (bottom wave / reflection) ---
        fill_bot = QPainterPath(bot_path)
        fill_bot.lineTo(w, mid)
        fill_bot.lineTo(0, mid)
        fill_bot.closeSubpath()

        grad_bot = QLinearGradient(0, mid, 0, h)
        grad_bot.setColorAt(0.0, fill_color_mid)
        grad_bot.setColorAt(1.0, QColor(self._color.red(), self._color.green(), self._color.blue(), 15))
        painter.setBrush(QBrush(grad_bot))
        painter.drawPath(fill_bot)

        # --- glow + line (top) ---
        self._draw_glow(painter, top_path, self._color)

        # --- glow + line (bottom / reflection, dimmer) ---
        dim_color = QColor(
            int((self._color.red() + ACCENT_DIM.red()) / 2),
            int((self._color.green() + ACCENT_DIM.green()) / 2),
            int((self._color.blue() + ACCENT_DIM.blue()) / 2),
        )
        self._draw_glow(painter, bot_path, dim_color, alpha_scale=0.4)

        # --- center line ---
        center_pen = QPen(QColor(255, 255, 255, 18))
        center_pen.setWidth(1)
        painter.setPen(center_pen)
        painter.drawLine(0, int(mid), w, int(mid))

        painter.end()

    @staticmethod
    def _draw_glow(
        painter: QPainter,
        path: QPainterPath,
        color: QColor,
        alpha_scale: float = 1.0,
    ) -> None:
        for extra_w, alpha_mult in GLOW_LAYERS:
            c = QColor(color)
            c.setAlphaF(min(1.0, alpha_mult * alpha_scale))
            pen = QPen(c)
            pen.setWidthF(1.0 + extra_w)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
