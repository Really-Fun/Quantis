from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QSlider
from qasync import asyncSlot

from models import UserPlaylist
from player import Player


class PlayMenu(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.tool_layout = QHBoxLayout()

        self.main_layout.addLayout(self.tool_layout)

        #main logic
        self.current_playlist = UserPlaylist.get_playlist_from_path("playlists/english.json")
        self.player = Player()

        self.btn_play = self.create_button("assets/icons/play.png", 65)
        self.btn_next = self.create_button("assets/icons/forward.png",)
        self.btn_prev = self.create_button("assets/icons/backward.png",)
        self.btn_wave = self.create_button("assets/icons/wave.png", 40)
        self.btn_repeat = self.create_button("assets/icons/repeat_playlist.png", 40)
        self.btn_download = self.create_button("assets/icons/download.png", 40)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(self.change_volume)

        self.btn_next.clicked.connect(self.play_next_track)

        self.tool_layout.addWidget(self.btn_wave)
        self.tool_layout.addWidget(self.btn_repeat)
        self.tool_layout.addWidget(self.volume_slider)
        self.tool_layout.addStretch(40)
        self.tool_layout.addWidget(self.btn_prev)
        self.tool_layout.addWidget(self.btn_play)
        self.tool_layout.addWidget(self.btn_next)
        self.tool_layout.addStretch(60)
        self.tool_layout.addWidget(self.btn_download)

    @asyncSlot()
    async def play_next_track(self):
        await self.player.play_track(self.current_playlist.move_next_track())

    def change_volume(self):
        self.player.volume = self.volume_slider.value()

    @staticmethod
    def create_button(icon_path: str, size: int | float = 50.0) -> QToolButton:
        btn = QToolButton()

        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(QSize(int(size * 0.55), int(size * 0.55)))
        btn.setFixedSize(QSize(size, size))
        btn.setCursor(Qt.PointingHandCursor)

        btn.setStyleSheet(f"""
                QToolButton {{
                    border-radius: {size // 2}px;
                    border: 2px solid #3a3a3a;
                    background: transparent;
                    border: none;
                }}""")

        return btn