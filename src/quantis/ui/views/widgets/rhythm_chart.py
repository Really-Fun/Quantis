"""«Когда слушаешь»: столбики по часам суток и по дням недели."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from quantis.ui.design_tokens import ACCENT_FALLBACK
from quantis.ui.fonts import app_font
from quantis.ui.views.widgets.delegate_paint_kit import paint_colors

WEEKDAYS = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
WEEKDAYS_FULL = (
    "понедельник",
    "вторник",
    "среда",
    "четверг",
    "пятница",
    "суббота",
    "воскресенье",
)


def listens_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} прослушивание"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} прослушивания"
    return f"{count} прослушиваний"


class BarChart(QWidget):
    """Вертикальные столбики с подписями снизу; пиковый — ярче."""

    def __init__(
        self,
        labels: Sequence[str],
        *,
        label_every: int = 1,
        tooltip_names: Sequence[str] | None = None,
        height: int = 150,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._labels = list(labels)
        self._names = list(tooltip_names or labels)
        self._label_every = max(1, label_every)
        self._values = [0] * len(self._labels)
        self._hover = -1
        self._accent = QColor(ACCENT_FALLBACK)
        self.setMouseTracking(True)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_accent(self, color: QColor) -> None:
        if color.isValid():
            self._accent = QColor(color)
            self.update()

    def set_values(self, values: Sequence[int]) -> None:
        self._values = [max(0, int(v)) for v in values][: len(self._labels)]
        self._values += [0] * (len(self._labels) - len(self._values))
        self.update()

    def _slot(self) -> float:
        return self.width() / max(1, len(self._labels))

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        index = int(event.position().x() // self._slot())
        index = index if 0 <= index < len(self._labels) else -1
        if index != self._hover:
            self._hover = index
            if index >= 0:
                self.setToolTip(
                    f"{self._names[index]}: {listens_word(self._values[index])}"
                )
            self.update()

    def leaveEvent(self, event: object) -> None:
        self._hover = -1
        self.update()
        super().leaveEvent(event)  # type: ignore[arg-type]

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = paint_colors()
        label_h = 20
        chart_h = self.height() - label_h - 4
        slot = self._slot()
        bar_w = max(4.0, min(28.0, slot * 0.62))
        peak = max(self._values) if self._values else 0
        accent = self._accent
        painter.setFont(app_font(9, QFont.Weight.Medium))
        for index, value in enumerate(self._values):
            x = index * slot + (slot - bar_w) / 2
            groove = QRectF(x, 4, bar_w, chart_h - 4)
            path = QPainterPath()
            path.addRoundedRect(groove, bar_w / 2.5, bar_w / 2.5)
            painter.fillPath(path, colors.bg_hover)
            if peak > 0 and value > 0:
                h = max(bar_w * 0.8, (chart_h - 4) * value / peak)
                bar = QRectF(x, chart_h - h, bar_w, h)
                path = QPainterPath()
                path.addRoundedRect(bar, bar_w / 2.5, bar_w / 2.5)
                strong = value == peak or index == self._hover
                gradient = QLinearGradient(bar.topLeft(), bar.bottomLeft())
                gradient.setColorAt(
                    0.0,
                    QColor(
                        accent.red(),
                        accent.green(),
                        accent.blue(),
                        255 if strong else 190,
                    ),
                )
                gradient.setColorAt(
                    1.0,
                    QColor(
                        accent.red(),
                        accent.green(),
                        accent.blue(),
                        140 if strong else 70,
                    ),
                )
                painter.fillPath(path, gradient)
            if index % self._label_every == 0 or index == self._hover:
                painter.setPen(
                    colors.title if index == self._hover else colors.subtitle
                )
                painter.drawText(
                    QRectF(index * slot - 10, chart_h + 4, slot + 20, label_h),
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                    self._labels[index],
                )
        painter.end()


def hour_chart(parent: QWidget | None = None) -> BarChart:
    return BarChart(
        [f"{h:02d}" for h in range(24)],
        label_every=3,
        tooltip_names=[f"{h:02d}:00–{h:02d}:59" for h in range(24)],
        height=170,
        parent=parent,
    )


def weekday_chart(parent: QWidget | None = None) -> BarChart:
    names = [name.capitalize() for name in WEEKDAYS_FULL]
    return BarChart(WEEKDAYS, tooltip_names=names, height=150, parent=parent)
