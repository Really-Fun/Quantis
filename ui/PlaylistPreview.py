from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt


class PlaylistPreview(QWidget):
    def __init__(self, playlist, parent=None):
        super().__init__(parent)

        self.playlist = playlist
        self.setObjectName("PlaylistPreview")
        self.setFixedHeight(90)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(12)

        # ---------- COVER ----------
        self.cover = QLabel()
        self.cover.setFixedSize(64, 64)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setObjectName("Cover")

        if playlist.cover_path:
            pixmap = QPixmap(playlist.cover_path)
            self.cover.setPixmap(
                pixmap.scaled(
                    64, 64,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation
                )
            )
        else:
            self.cover.setText("🎵")

        # ---------- TEXT ----------
        self.text_layout = QVBoxLayout()
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
