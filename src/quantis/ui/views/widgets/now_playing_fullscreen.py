"""Полноэкранный Now Playing (blur-cover + stubs)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.ui.views.widgets.cover_art import load_cover_pixmap
from quantis.ui.views.widgets.source_badge import paint_source_badge
from quantis.ui.views.widgets.waveform_seek import WaveformSeekSlider


class NowPlayingFullscreen(QFrame):
    """Оверлей поверх content: большая обложка + waveform + lyrics stub."""

    closed = Signal()

    def __init__(
        self,
        path_provider: PathProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("nowPlayingFullscreen")
        self._path_provider = path_provider
        self._track: Track | None = None
        self._bg = QPixmap()
        self._bg_scaled = QPixmap()
        self._bg_size = (0, 0)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(16)

        top = QHBoxLayout()
        self._close_btn = QPushButton("Закрыть")
        self._close_btn.setObjectName("nowPlayingStubBtn")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.clicked.connect(self.closed.emit)
        top.addStretch()
        top.addWidget(self._close_btn)
        layout.addLayout(top)

        self._cover = QLabel()
        self._cover.setFixedSize(320, 320)
        self._cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignHCenter)

        self._title = QLabel("")
        self._title.setObjectName("nowPlayingTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._title.setWordWrap(True)
        layout.addWidget(self._title)

        self._artist = QLabel("")
        self._artist.setObjectName("nowPlayingArtist")
        self._artist.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._artist)

        self._wave = WaveformSeekSlider()
        self._wave.setFixedHeight(56)
        layout.addWidget(self._wave)

        self._lyrics = QLabel("Текст песни появится здесь")
        self._lyrics.setObjectName("nowPlayingArtist")
        self._lyrics.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._lyrics.setWordWrap(True)
        layout.addWidget(self._lyrics)
        layout.addStretch(1)

        self.hide()

    def set_track(self, track: Track | None) -> None:
        self._track = track
        if track is None:
            self._title.setText("")
            self._artist.setText("")
            self._cover.clear()
            self._bg = QPixmap()
            self._bg_scaled = QPixmap()
            self._bg_size = (0, 0)
            self.update()
            return
        self._title.setText(track.title)
        self._artist.setText(track.author)
        path = Path(self._path_provider.get_cover_path(track))
        pix = load_cover_pixmap(path, 320)
        if pix is not None and not pix.isNull():
            painted = QPixmap(320, 320)
            painted.fill(Qt.GlobalColor.transparent)
            painter = QPainter(painted)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.drawPixmap(0, 0, pix)
            paint_source_badge(painter, painted.rect(), str(track.source), size=22)
            painter.end()
            self._cover.setPixmap(painted)
            self._bg = pix
            self._bg_scaled = QPixmap()
            self._bg_size = (0, 0)
        else:
            self._cover.clear()
            self._bg = QPixmap()
            self._bg_scaled = QPixmap()
            self._bg_size = (0, 0)
        self.update()

    def _scaled_bg(self) -> QPixmap:
        if self._bg.isNull():
            return self._bg
        size = (self.width(), self.height())
        if not self._bg_scaled.isNull() and self._bg_size == size:
            return self._bg_scaled
        w, h = size
        longest = max(w, h)
        if longest > 960:
            scale = 960 / longest
            w = max(1, int(w * scale))
            h = max(1, int(h * scale))
        self._bg_scaled = self._bg.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.FastTransformation,
        )
        self._bg_size = size
        return self._bg_scaled

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(11, 13, 18, 230))
        scaled = self._scaled_bg()
        if not scaled.isNull():
            painter.setOpacity(0.22)
            painter.drawPixmap(self.rect(), scaled)
            painter.setOpacity(1.0)
        painter.end()
        super().paintEvent(event)
