"""Правая колонка Now Playing."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.ui.cover_prefetch import schedule_cover_prefetch
from quantis.ui.views.widgets.cover_art import load_cover_pixmap
from quantis.ui.views.widgets.source_badge import paint_source_badge


class _CoverWithBadge(QLabel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nowPlayingCover")
        self.setFixedSize(220, 220)
        self.setScaledContents(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._source: str | None = None
        self._pixmap = QPixmap()

    def set_cover(self, pixmap: QPixmap | None, source: str | None) -> None:
        self._source = source
        self._pixmap = pixmap if pixmap is not None else QPixmap()
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(28, 33, 45))
        painter.drawRoundedRect(rect, 16, 16)

        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                rect.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = rect.x() + (rect.width() - scaled.width()) // 2
            y = rect.y() + (rect.height() - scaled.height()) // 2
            clip = QPainterPath()
            clip.addRoundedRect(rect, 16, 16)
            painter.setClipPath(clip)
            painter.drawPixmap(x, y, scaled)
            painter.setClipping(False)

        if self._source:
            paint_source_badge(painter, rect, self._source, size=20)
        painter.end()


class NowPlayingPanel(QFrame):
    """Опциональная правая колонка ~300px."""

    source_action_requested = Signal()
    lyrics_requested = Signal()
    queue_requested = Signal()

    def __init__(
        self,
        path_provider: PathProvider,
        *,
        bridge=None,
        music=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("nowPlayingPanel")
        self.setFixedWidth(300)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._path_provider = path_provider
        self._bridge = bridge
        self._music = music
        self._track: Track | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(12)

        self._eyebrow = QLabel("СЕЙЧАС")
        self._eyebrow.setObjectName("sectionTitle")
        layout.addWidget(self._eyebrow)

        self._cover = _CoverWithBadge()
        layout.addWidget(self._cover, 0, Qt.AlignmentFlag.AlignHCenter)

        self._title = QLabel("Выберите трек")
        self._title.setObjectName("nowPlayingTitle")
        self._title.setWordWrap(True)
        self._title.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._title)

        self._artist = QLabel("")
        self._artist.setObjectName("nowPlayingArtist")
        self._artist.setWordWrap(True)
        self._artist.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._artist)

        self._source_btn = QPushButton("Источник")
        self._source_btn.setObjectName("nowPlayingSourceBtn")
        self._source_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._source_btn.setToolTip("Слушать в оригинале / сменить источник (скоро)")
        self._source_btn.clicked.connect(self.source_action_requested.emit)
        layout.addWidget(self._source_btn)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._lyrics_btn = QPushButton("Текст")
        self._lyrics_btn.setObjectName("nowPlayingStubBtn")
        self._lyrics_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._lyrics_btn.clicked.connect(self.lyrics_requested.emit)
        self._queue_btn = QPushButton("Очередь")
        self._queue_btn.setObjectName("nowPlayingStubBtn")
        self._queue_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._queue_btn.clicked.connect(self.queue_requested.emit)
        actions.addWidget(self._lyrics_btn)
        actions.addWidget(self._queue_btn)
        layout.addLayout(actions)

        layout.addStretch(1)

    def set_track(self, track: Track | None) -> None:
        self._track = track
        if track is None:
            self._title.setText("Выберите трек")
            self._artist.setText("")
            self._cover.set_cover(None, None)
            self._source_btn.setText("Источник")
            return

        self._title.setText(track.title)
        self._artist.setText(track.author)
        source = str(getattr(track, "source", "") or "")
        label = (
            "YouTube"
            if source.lower() == "youtube"
            else "Яндекс" if source.lower() == "yandex" else "Источник"
        )
        self._source_btn.setText(f"Источник · {label}")
        self._apply_cover(track)
        if self._bridge is not None and self._music is not None:
            schedule_cover_prefetch(
                [track],
                self._music.downloader,
                self._bridge,
                on_done=lambda t=track: self._apply_cover(t),
                limit=1,
            )

    def _apply_cover(self, track: Track) -> None:
        if self._track is not track:
            return
        path = Path(self._path_provider.get_cover_path(track))
        pixmap = load_cover_pixmap(path, 220)
        self._cover.set_cover(pixmap, str(getattr(track, "source", "") or ""))
