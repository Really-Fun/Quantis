from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton


class PlayMenu(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.tool_layout = QHBoxLayout()

        self.btn_play = self.create_button("assets/icons/play.png", 50)
        self.btn_next = self.create_button("assets/icons/forward.png", 35)
        self.btn_prev = self.create_button("assets/icons/backward.png", 35)
        self.btn_wave = self.create_button("assets/icons/wave.png", 25)
        self.btn_repeat = self.create_button("assets/icons/repeat_playlist.png", 25)
        self.btn_download = self.create_button("assets/icons/download.png", 25)

        self.tool_layout.addWidget(self.btn_wave)
        self.tool_layout.addWidget(self.btn_repeat)
        self.tool_layout.addStretch(45)
        self.tool_layout.addWidget(self.btn_prev)
        self.tool_layout.addWidget(self.btn_play)
        self.tool_layout.addWidget(self.btn_next)
        self.tool_layout.addStretch(55)
        self.tool_layout.addWidget(self.btn_download)

        self.main_layout.addLayout(self.tool_layout)

    @staticmethod
    def create_button(icon_path: str, size: int | float = 50.0) -> QToolButton:
        btn = QToolButton()

        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(QSize(int(size * 0.55), int(size * 0.55)))
        btn.setFixedSize(QSize(size, size))
        btn.setAttribute(Qt.WA_TranslucentBackground)
        btn.setCursor(Qt.PointingHandCursor)

        return btn