from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QSizePolicy
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt

from providers import PathProvider


class PlaylistPreview(QWidget):
    def __init__(self, playlist, parent=None):
        super().__init__(parent)

        self.path_provider = PathProvider()
        self.setObjectName("MiniTrack")
        self.setFixedHeight(100)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.setSpacing(12)

        # ---------- COVER ----------
        self.cover = QLabel()
        self.cover.setFixedSize(45, 45)
        self.cover.setAlignment(Qt.AlignCenter)
        self.cover.setObjectName("Cover")

        pixmap = QPixmap("covers/631110.jpg")
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

        self.text_layout.addWidget(self.title)
        self.text_layout.addStretch()

        self.main_layout.addWidget(self.cover)
        self.main_layout.addLayout(self.text_layout)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed
        )