"""Промо-карточка «Моя волна» на главной."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import (
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor
from quantis.ui.views.widgets.home_pill_badge import HomePillBadge


class _WaveMark(QWidget):
    """Декоративный знак волны слева на карточке."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(56, 56)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(2, 2, -2, -2)
        path = QPainterPath()
        path.addEllipse(rect)

        colors = UiPreferences().theme.colors
        hl = qcolor(colors.hl_rgb)
        hl.setAlpha(70)
        accent = qcolor(colors.accent_fallback)
        accent.setAlpha(50)
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        fill.setColorAt(0.0, hl)
        fill.setColorAt(1.0, accent)
        painter.fillPath(path, fill)

        hl.setAlpha(90)
        pen = QPen(hl)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.drawPath(path)

        mark = qcolor(colors.hl_rgb)
        mark.setAlpha(230)
        painter.setPen(mark)
        font = painter.font()
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "≈")
        painter.end()


class WavePromoCard(QFrame):
    """Карточка «Моя волна» — рядом с hero или отдельной полосой."""

    open_requested = Signal()
    play_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("wavePromoCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(72)
        self.setMaximumHeight(168)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._available = False
        self._track_count = 0
        self._source_label = "Yandex Music"
        self._hovered = False

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 14, 14, 14)
        root.setSpacing(14)

        root.addWidget(_WaveMark(), 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(5)
        text.setContentsMargins(0, 2, 0, 2)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self._badge = HomePillBadge("Моя волна", variant="wave")
        title_row.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self._count_label = QLabel("")
        self._count_label.setObjectName("wavePromoCount")
        title_row.addWidget(self._count_label, 0, Qt.AlignmentFlag.AlignVCenter)
        title_row.addStretch(1)
        text.addLayout(title_row)

        self._subtitle = QLabel("Персональное радио · нужен токен Yandex")
        self._subtitle.setObjectName("wavePromoSubtitle")
        self._subtitle.setWordWrap(True)
        text.addWidget(self._subtitle)
        text.addStretch(1)
        root.addLayout(text, stretch=1)

        self._play_btn = QToolButton()
        self._play_btn.setObjectName("wavePromoPlayBtn")
        self._play_btn.setText("▶")
        self._play_btn.setToolTip("Слушать волну")
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setEnabled(False)
        self._play_btn.clicked.connect(self.play_requested.emit)
        root.addWidget(self._play_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_state(
        self,
        *,
        available: bool,
        track_count: int = 0,
        source: str = "yandex",
        loading: bool = False,
        error: str | None = None,
    ) -> None:
        self._available = available
        self._track_count = track_count
        self._source_label = "Yandex Music" if source == "yandex" else source
        self._play_btn.setEnabled(available and track_count > 0 and not loading)
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if available
            else Qt.CursorShape.ArrowCursor
        )

        if loading:
            self._subtitle.setText(f"Загружаем · {self._source_label}…")
            self._count_label.setText("")
        elif error:
            self._subtitle.setText(error)
            self._count_label.setText("")
        elif available and track_count:
            self._subtitle.setText(f"{self._source_label} · нажми, чтобы открыть поток")
            self._count_label.setText(f"{track_count} в потоке")
        elif available:
            self._subtitle.setText(f"{self._source_label} · пока пусто")
            self._count_label.setText("")
        else:
            self._subtitle.setText("Добавь OAuth-токен Yandex во вкладке Member")
            self._count_label.setText("")
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._available:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)

        colors = UiPreferences().theme.colors
        hl = qcolor(colors.hl_rgb)
        ink = qcolor(colors.ink_rgb)
        fill = QLinearGradient(rect.topLeft(), rect.bottomRight())
        top_alpha = 22 if self._available else 8
        if self._hovered and self._available:
            top_alpha = 32
        hl.setAlpha(top_alpha)
        ink.setAlpha(8 if self._available else 5)
        fill.setColorAt(0.0, hl)
        fill.setColorAt(1.0, ink)
        painter.fillPath(path, fill)

        border = qcolor(colors.hl_rgb)
        border.setAlpha(28 if not self._available else (95 if self._hovered else 60))
        pen = QPen(border)
        pen.setWidthF(1.15)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()
