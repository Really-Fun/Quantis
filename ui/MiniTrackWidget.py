import os

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QHBoxLayout,
    QVBoxLayout,
    QSizePolicy
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from qasync import asyncSlot

from models import Track
from providers import PathProvider
from services import AsyncDownloader


class MiniTrackWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.path_provider = PathProvider()
        self.downloader = AsyncDownloader()

        self.setObjectName("MiniTrack")
        self.setFixedHeight(64)
        self.setFixedWidth(160)

        # ---------- MAIN LAYOUT ----------
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(12, 8, 12, 8)
        self.main_layout.setSpacing(12)

        # ---------- COVER ----------
        self.cover = QLabel()
        self.cover.setFixedSize(48, 48)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setObjectName("Cover")

        pixmap = QPixmap("covers/631110.jpg")
        self.cover.setPixmap(
            pixmap.scaled(
                48, 48,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
        )

        # ---------- TEXT ----------
        self.text_layout = QVBoxLayout()
        self.text_layout.setSpacing(2)
        self.text_layout.setContentsMargins(0, 0, 0, 0)

        self.title = QLabel("Very long track name like in Spotify")
        self.title.setObjectName("Title")
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.title.setWordWrap(False)
        self.title.setTextInteractionFlags(Qt.NoTextInteraction)
        self.title.setMaximumHeight(20)

        self.artist = QLabel("Artist name")
        self.artist.setObjectName("Artist")
        self.artist.setMaximumHeight(16)

        self.text_layout.addWidget(self.title)
        self.text_layout.addWidget(self.artist)

        # ---------- ASSEMBLE ----------
        self.main_layout.addWidget(self.cover)
        self.main_layout.addLayout(self.text_layout)
        self.main_layout.addStretch()

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    @asyncSlot()
    async def update_widget(self, track: Track):
        path = self.path_provider.get_cover_path(track)
        if not os.path.exists(path):
            await self.downloader.download_cover(track)
        pixmap = QPixmap(path)
        self.cover.setPixmap(pixmap.scaled(48, 48,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation))
        self.title.setText(track.title)
        self.artist.setText(track.author)