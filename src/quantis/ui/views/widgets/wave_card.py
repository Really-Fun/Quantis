"""Карточка «Моя волна» справа от сцены главной: пока очередь пуста.

Стеклянная, как «Дальше», и того же размера: когда в очереди появляются
треки, главная показывает на её месте «Дальше».
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPaintEvent, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

from quantis.services.async_wave import WaveMood
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor
from quantis.ui.views.widgets.glass import paint_glass
from quantis.ui.views.widgets.wave_moods import WaveMoodStrip


class WaveCard(QWidget):
    play_requested = Signal()
    open_requested = Signal()
    """Страница «Моя волна» с картой настроений."""
    mood_activated = Signal(object)
    """WaveMood, по которому включить волну."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("homeWaveCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self.update)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(6)

        kicker = QLabel("МОЯ ВОЛНА")
        kicker.setObjectName("homeWaveKicker")
        root.addWidget(kicker)

        title = QLabel("Поток под твой вкус")
        title.setObjectName("homeWaveTitle")
        title.setWordWrap(True)
        root.addWidget(title)

        self._status = QLabel()
        self._status.setObjectName("homeWaveStatus")
        root.addWidget(self._status)

        root.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._play_btn = QToolButton()
        self._play_btn.setObjectName("homeWavePlay")
        self._play_btn.setText("▶  Слушать")
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setToolTip("Включить «Мою волну»")
        self._play_btn.clicked.connect(self.play_requested.emit)
        actions.addWidget(self._play_btn)
        self._open_btn = QToolButton()
        self._open_btn.setObjectName("homeSectionAction")
        self._open_btn.setText("Настроения")
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.setToolTip("Карта настроений и занятий")
        self._open_btn.clicked.connect(self.open_requested.emit)
        actions.addWidget(self._open_btn)
        actions.addStretch(1)
        root.addLayout(actions)

        root.addSpacing(8)
        self._moods = WaveMoodStrip()
        self._moods.mood_activated.connect(self.mood_activated.emit)
        self._moods.hide()
        root.addWidget(self._moods)

        self.set_state(track_count=0, loading=True)

    @property
    def play_button(self) -> QToolButton:
        return self._play_btn

    @property
    def open_button(self) -> QToolButton:
        return self._open_btn

    @property
    def moods(self) -> WaveMoodStrip:
        return self._moods

    @property
    def status_text(self) -> str:
        return self._status.text()

    def set_state(
        self, *, track_count: int, loading: bool = False, error: str = ""
    ) -> None:
        if error:
            text = error
        elif loading:
            text = "Загружаем…"
        elif track_count:
            text = f"{track_count} в потоке"
        else:
            text = "Подберём треки по твоей истории"
        self._status.setText(text)
        self._play_btn.setEnabled(not loading)

    def set_moods(
        self,
        moods: Sequence[WaveMood],
        *,
        active_seeds: Sequence[str] = (),
        busy: bool = False,
    ) -> None:
        self._moods.set_moods(moods, active_seeds=active_seeds, busy=busy)
        self._moods.setVisible(bool(moods))

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = self._prefs.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 22, 22)
        if not paint_glass(self, painter, path):
            painter.fillPath(path, qcolor(theme.colors.surface))
        border = qcolor(theme.colors.ink_rgb)
        border.setAlpha(26)
        painter.setPen(QPen(border, 1))
        painter.drawPath(path)
        painter.end()
