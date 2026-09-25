from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
)

from quantis.models import Track
from quantis.ui.cover_accent import accent_from_cover_path, fallback_accent
from quantis.ui.views.widgets.cover_art import load_track_cover, track_cover_file
from quantis.ui.views.widgets.elided_label import ElidedLabel
from quantis.ui.views.widgets.home_pill_badge import HomePillBadge
from quantis.ui.views.widgets.playlist_card import GradientCover


class FeaturedTrackPanel(QFrame):
    """Hero «Продолжить слушать» — цвет из обложки, клик по всей карточке."""

    play_requested = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("featuredPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setMinimumHeight(148)
        self.setMaximumHeight(168)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._track: Track | None = None
        self._index = 0
        self._is_playing = False
        self._hovered = False
        self._accent = fallback_accent()

        root = QHBoxLayout(self)
        root.setContentsMargins(14, 14, 16, 14)
        root.setSpacing(18)

        self._cover = GradientCover("Quantis", size=124, radius=16)
        root.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(4)
        col.setContentsMargins(0, 6, 0, 6)

        self._eyebrow = HomePillBadge("Продолжить слушать", variant="continue")
        col.addWidget(self._eyebrow, 0, Qt.AlignmentFlag.AlignLeft)

        self._title = ElidedLabel("Выбери трек", max_lines=2)
        self._title.setObjectName("featuredTitle")
        col.addWidget(self._title)

        self._author = QLabel("Открой поиск или плейлист")
        self._author.setObjectName("featuredAuthor")
        self._author.setWordWrap(True)
        col.addWidget(self._author)

        col.addStretch(1)
        root.addLayout(col, stretch=1)

        self._play_btn = QToolButton()
        self._play_btn.setObjectName("featuredPlayBtn")
        self._play_btn.setText("▶")
        self._play_btn.setToolTip("Слушать")
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.clicked.connect(self._emit_play)
        root.addWidget(self._play_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_track(
        self, track: Track | None, index: int = 0, *, playing: bool = False
    ) -> None:
        self._track = track
        self._index = index
        self._is_playing = playing
        self._play_btn.setEnabled(track is not None)
        self._play_btn.setText("❚❚" if playing else "▶")
        self._play_btn.setToolTip("Пауза" if playing else "Слушать")
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if track is not None
            else Qt.CursorShape.ArrowCursor
        )

        if track is None:
            self._title.setText("Готов к сессии")
            self._author.setText("Открой поиск или плейлист")
            self._cover.set_content("Quantis", None, source_key="")
            self._accent = fallback_accent()
        else:
            self._title.setText(track.title)
            self._author.setText(track.author)
            path = str(track_cover_file(track))
            load_track_cover(track, 124)
            self._cover.set_content(track.title, path, source_key=str(track.source))
            self._accent = accent_from_cover_path(path)
            if not self._accent.isValid():
                self._accent = fallback_accent()
        self._cover.set_play_overlay(self._hovered and not playing)
        self.update()

    def _emit_play(self) -> None:
        if self._track is not None:
            self.play_requested.emit(self._index)

    def mouseReleaseEvent(self, event) -> None:
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._track is not None
            and self.childAt(event.position().toPoint()) is not self._play_btn
        ):
            self._emit_play()
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._cover.set_play_overlay(self._track is not None and not self._is_playing)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._cover.set_play_overlay(False)
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 18, 18)

        accent = QColor(self._accent)
        left = QColor(accent)
        left.setAlpha(70 if self._is_playing else (58 if self._hovered else 36))
        mid = QColor(255, 255, 255)
        mid.setAlpha(16 if self._hovered or self._is_playing else 10)
        right = QColor(255, 255, 255, 6)

        fill = QLinearGradient(rect.topLeft(), rect.topRight())
        fill.setColorAt(0.0, left)
        fill.setColorAt(0.42, mid)
        fill.setColorAt(1.0, right)
        painter.fillPath(path, fill)

        border = QColor(accent)
        border.setAlpha(120 if self._is_playing else (90 if self._hovered else 48))
        pen = QPen(border)
        pen.setWidthF(1.15)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()
