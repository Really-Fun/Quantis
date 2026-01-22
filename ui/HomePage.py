import colorsys

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QSizePolicy, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QTimer

from models import UserPlaylist
from ui.PlaylistPreview import PlaylistPreview

class HomePage(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("HomePage")

        self.main_layout = QVBoxLayout(self)

        self.main_label = QLabel("Главная")
        self.main_label.setObjectName("Header")
        self.main_label.setAlignment(Qt.AlignCenter)
        self.main_label.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed
        )

        self.main_layout.addWidget(self.main_label)
        self.main_layout.addStretch()
        self.main_layout.addWidget(PlaylistPreview(UserPlaylist.get_playlist_from_path("playlists/english.json")))

        # ---------- базовый стиль ----------
        self.main_label.setStyleSheet("""
        QLabel#Header {
            padding: 14px;
            font-size: 24px;
            color: white;
            border: 2px solid cyan;
            border-radius: 12px;
            background: transparent;
        }
        """)

        # ---------- НАСТОЯЩИЙ НЕОН ----------
        self.glow = QGraphicsDropShadowEffect(self)
        self.glow.setBlurRadius(30)
        self.glow.setOffset(0, 0)
        self.glow.setColor(QColor(0, 255, 255))

        self.main_label.setGraphicsEffect(self.glow)

        # ---------- анимация ----------
        self._hue = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_glow)
        self.timer.start(30)  # скорость перелива

    def update_glow(self):
        self._hue = (self._hue + 0.004) % 1.0
        r, g, b = colorsys.hsv_to_rgb(self._hue, 1, 1)

        color = QColor(
            int(r * 255),
            int(g * 255),
            int(b * 255)
        )

        # цвет свечения
        self.glow.setColor(color)

        # цвет рамки
        self.main_label.setStyleSheet(f"""
        QLabel#Header {{
            padding: 14px;
            font-size: 24px;
            color: white;
            border: 2px solid rgb({color.red()}, {color.green()}, {color.blue()});
            border-radius: 12px;
            background: transparent;
        }}
        """)