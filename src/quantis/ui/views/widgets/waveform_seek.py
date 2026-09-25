from __future__ import annotations

import math
import random

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QLinearGradient, QPainter, QPaintEvent
from PySide6.QtWidgets import QSlider, QStyle, QStyleOptionSlider, QWidget

from quantis.ui.cover_accent import CoverPalette
from quantis.ui.live_palette import LivePalette
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor


class WaveformSeekSlider(QSlider):
    """Перемотка по «форме волны»: сыгранное — градиентом цветов трека
    (``accent2 → accent``), остальное — полупрозрачными «чернилами» темы.

    Пока нет настоящей огибающей трека, форма волны своя у каждого трека
    (зерно — ключ трека), чтобы треки не выглядели одинаково.
    """

    STEP, BAR = 4, 2.4

    def __init__(
        self,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent)
        self.setObjectName("waveformSeek")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._palette = LivePalette.instance().current
        self._peaks: list[float] = []
        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self._on_theme)
        self._on_theme()
        self.set_seed("")
        LivePalette.instance().palette_changed.connect(self._on_palette)

    def _on_theme(self) -> None:
        colors = self._prefs.theme.colors
        self._rest = qcolor(colors.ink_rgb)
        self._rest.setAlpha(52)
        self._handle = qcolor(colors.handle)
        self.update()

    def set_seed(self, key: str) -> None:
        rnd = random.Random(key)
        raw = [rnd.random() for _ in range(400)]
        smooth = []
        for i in range(len(raw)):
            window = raw[max(0, i - 2) : i + 3]
            smooth.append(sum(window) / len(window))
        self._peaks = [
            0.18
            + 0.82
            * math.pow(v, 1.4)
            * (0.55 + 0.45 * math.sin(i / 400 * math.pi * 3 + 1) ** 2)
            for i, v in enumerate(smooth)
        ]
        self.update()

    def _on_palette(self, palette: CoverPalette) -> None:
        self._palette = palette
        if self.isVisible():
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(
            QStyle.ComplexControl.CC_Slider,
            opt,
            QStyle.SubControl.SC_SliderGroove,
            self,
        )
        if groove.width() <= 0:
            groove = self.rect()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        span = max(1, self.maximum() - self.minimum())
        progress = (self.value() - self.minimum()) / span if self.maximum() > 0 else 0.0
        left, width, h = groove.left(), groove.width(), self.height()
        head = left + width * progress
        gradient = QLinearGradient(left, 0, max(left + 1.0, head), 0)
        gradient.setColorAt(0, self._palette.accent2)
        gradient.setColorAt(1, self._palette.accent)
        played, rest = QBrush(gradient), QBrush(self._rest)
        count = max(1, int(width // self.STEP))
        for i in range(count):
            peak = self._peaks[int(i / count * len(self._peaks))]
            bar_h = max(2.0, (h - 4) * peak)
            x = left + i * self.STEP
            painter.setBrush(played if x < head else rest)
            painter.drawRoundedRect(
                QRectF(x, (h - bar_h) / 2, self.BAR, bar_h), 1.2, 1.2
            )
        painter.setBrush(self._handle)
        painter.drawRoundedRect(QRectF(head - 1, 0, 2, h), 1, 1)
        painter.end()
