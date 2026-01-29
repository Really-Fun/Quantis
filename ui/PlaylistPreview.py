from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, Signal

from providers import PathProvider


class PlaylistPreview(QWidget):
    clicked = Signal(object)

    def __init__(self, playlist, parent=None):
        super().__init__(parent)

        self.path_provider = PathProvider()
        self.playlist = playlist
        self.setObjectName("PlaylistPreview")
        self.setFixedHeight(160)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(12)

        # ---------- COVER ----------
        self.cover = QLabel()
        self.cover.setFixedSize(120,120)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setObjectName("Cover")

        if not playlist.cover_path:
            playlist.cover_path = self.path_provider.get_cover_path(playlist.tracks.values[0])

        pixmap = QPixmap(playlist.cover_path)
        self.cover.setPixmap(
            pixmap.scaled(
                120, 120,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation
            )
        )

        # ---------- TEXT ----------
        self.text_layout = QHBoxLayout()
        self.text_layout.setSpacing(4)

        self.title = QLabel(playlist.name)
        self.title.setObjectName("Title")

        self.count = QLabel(f"{len(playlist.tracks.values)} треков")
        self.count.setObjectName("Count")

        self.text_layout.addWidget(self.title)
        self.text_layout.addWidget(self.count)
        self.text_layout.addStretch()

        self.main_layout.addWidget(self.cover)
        self.main_layout.addLayout(self.text_layout)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed
        )

        self.setStyleSheet("""
        QWidget#PlaylistPreview {
            border-radius: 12px;
            background-color: rgba(255, 255, 255, 0.04);
        }

        QWidget#PlaylistPreview:hover {
            background-color: rgba(0, 255, 240, 0.08);
        }

        QLabel#Title {
            font-size: 15px;
            font-weight: 600;
            color: white;
        }

        QLabel#Count {
            font-size: 12px;
            color: #9a9a9a;
        }

        QLabel#Cover {
            border-radius: 8px;
            background-color: #222;
        }
        """)

    def mousePressEvent(self, event, /):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.playlist)