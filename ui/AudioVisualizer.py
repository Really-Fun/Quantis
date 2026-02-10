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

# --- Константы ---
_REFRESH_MS: int = 25
_DECAY: float = 0.88
_SMOOTHING: float = 0.35
_MIN_BARS: int = 8
_FREQ_MIN: float = 40.0
_FREQ_MAX: float = 10000.0
_MID_RATIO: float = 0.45
_AMPLITUDE: float = 0.40
_GAIN: float = 2.2

# Glow layers: (extra width, alpha multiplier)
_GLOW_LAYERS: list[tuple[int, float]] = [
    (12, 0.06),
    (8, 0.10),
    (5, 0.18),
    (3, 0.35),
    (1, 0.90),
]


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

        t = _SMOOTHING
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


class AudioVisualizer(QWidget):
    """Неоновая волна с glow-эффектом и зеркальным отражением."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        bar_count: int = 64,
        height: int = 120,
    ) -> None:
        super().__init__(parent)

        self._bar_count = max(_MIN_BARS, int(bar_count))
        self._levels: list[float] = [0.0] * self._bar_count

        self.setFixedHeight(int(height))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._viz = VizualPlayer()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(_REFRESH_MS)

    # --- FFT -> levels ---

    def _update_levels(self) -> None:
        targets = self._raw_levels()
        for i in range(self._bar_count):
            target = max(0.0, min(1.0, targets[i]))
            self._levels[i] = max(target, self._levels[i] * _DECAY)

    def _raw_levels(self) -> list[float]:
        res = self._viz.get_fft()
        if res is None:
            return [0.0] * self._bar_count

        freqs, mags = res
        if mags.size == 0:
            return [0.0] * self._bar_count

        mask = (freqs >= _FREQ_MIN) & (freqs <= _FREQ_MAX)
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
            boosted = min(1.0, level * _GAIN)
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

        mid = h * _MID_RATIO
        amplitude = h * _AMPLITUDE

        top_pts = self._make_points(w, mid, amplitude, flip=False)
        bot_pts = self._make_points(w, mid, amplitude, flip=True)

        top_path = _build_smooth_path(top_pts)
        bot_path = _build_smooth_path(bot_pts)

        # Fill gradient (subtle area under/over curve)
        fill_color_top = QColor(0, 220, 255, 25)
        fill_color_mid = QColor(0, 220, 255, 0)

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
        grad_bot.setColorAt(1.0, QColor(0, 220, 255, 15))
        painter.setBrush(QBrush(grad_bot))
        painter.drawPath(fill_bot)

        # --- glow + line (top) ---
        self._draw_glow(painter, top_path, QColor(0, 220, 255))

        # --- glow + line (bottom / reflection, dimmer) ---
        self._draw_glow(painter, bot_path, QColor(0, 180, 255), alpha_scale=0.4)

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
        for extra_w, alpha_mult in _GLOW_LAYERS:
            c = QColor(color)
            c.setAlphaF(min(1.0, alpha_mult * alpha_scale))
            pen = QPen(c)
            pen.setWidthF(1.0 + extra_w)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawPath(path)
