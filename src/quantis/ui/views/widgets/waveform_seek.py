from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider


class WaveformSeekSlider(QSlider):
    """Waveform-seek с неоновым градиентом прогресса."""

    def __init__(self, orientation=Qt.Orientation.Horizontal, parent=None) -> None:
        super().__init__(orientation, parent)
        self.setObjectName("waveformSeek")
        self._bars = self._generate_bars(112)

    @staticmethod
    def _generate_bars(count: int) -> list[float]:
        import math

        bars: list[float] = []
        for i in range(count):
            t = i / max(count - 1, 1)
            v = (
                0.32
                + 0.28 * math.sin(t * math.pi * 5.2)
                + 0.2 * math.sin(t * math.pi * 11.7 + 0.4)
                + 0.14 * math.cos(t * math.pi * 2.1)
            )
            bars.append(max(0.14, min(1.0, v)))
        return bars

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            opt,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        if groove.width() <= 0:
            painter.end()
            return

        max_val = max(self.maximum(), 1)
        progress = self.value() / max_val
        bar_count = len(self._bars)
        gap = 2
        bar_w = max(2, (groove.width() - gap * (bar_count - 1)) // bar_count)
        base_y = groove.center().y()
        max_h = groove.height() + 16

        for i, amp in enumerate(self._bars):
            x = groove.left() + i * (bar_w + gap)
            h = int(max_h * amp)
            top = base_y - h // 2
            filled = (i / bar_count) <= progress

            if filled:
                grad = QLinearGradient(x, top, x + bar_w, top + h)
                grad.setColorAt(0.0, QColor(255, 42, 127, 230))
                grad.setColorAt(0.55, QColor(230, 59, 46, 240))
                grad.setColorAt(1.0, QColor(0, 229, 255, 220))
                painter.fillRect(x, top, bar_w, h, grad)
            else:
                painter.fillRect(x, top, bar_w, h, QColor(0, 229, 255, 22))

        handle_x = groove.left() + int(groove.width() * progress)
        glow = QRadialGradient(handle_x, base_y, 12)
        glow.setColorAt(0.0, QColor(0, 229, 255, 90))
        glow.setColorAt(1.0, QColor(0, 229, 255, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(handle_x - 12, base_y - 12, 24, 24)

        painter.setBrush(QColor(242, 240, 235))
        painter.drawEllipse(handle_x - 6, base_y - 6, 12, 12)
        painter.end()
