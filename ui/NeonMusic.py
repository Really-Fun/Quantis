"""Главное окно приложения."""
import sys

from PySide6.QtWidgets import (
    QMainWindow,
    QApplication,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from qasync import asyncSlot

from ui.MenuPlayWidget import PlayMenu
from ui.MenuTabsWidget import MenuTabs
from ui.Stack import Stack
from ui.AudioVisualizer import AudioVisualizer


class NeonMusic(QMainWindow):

    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("NeonMusic")
        self.resize(600, 800)
        self.setMaximumSize(1920, 1080)

        # ================== CENTRAL ==================
        central = QWidget(self)
        central.setObjectName("central")
        self.setCentralWidget(central)

        # ================== BACKGROUND ==================
        self.background = QLabel(central)
        self.background.setPixmap(QPixmap("assets/background/real.jpg")) #real.jpg
        self.background.setScaledContents(True)

        # ================== DARK OVERLAY ==================
        self.dark_overlay = QFrame(central)
        self.dark_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 150);
            }
        """)

        # ================== VISUALIZER (behind content) ==================
        self.visualizer = AudioVisualizer(central, bar_count=56, height=120)

        # z-order: background < overlay < visualizer < content
        self.background.lower()
        self.dark_overlay.stackUnder(self.visualizer)

        # ================== MAIN LAYOUT ==================
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ================== CONTENT (LEFT + RIGHT) ==================
        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # -------- LEFT MENU --------
        self.menu_tabs = MenuTabs()
        self.menu_tabs.setFixedWidth(self.width() // 3)
        self.menu_tabs.setAttribute(Qt.WA_TranslucentBackground)

        content_layout.addWidget(self.menu_tabs)

        # -------- RIGHT AREA --------
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.stack = Stack()
        right_layout.addWidget(self.stack, stretch=1)

        # -------- PLAY MENU (BOTTOM) --------
        self.play_menu = PlayMenu()
        self.play_menu.setFixedHeight(90)
        self.play_menu.setAttribute(Qt.WA_TranslucentBackground)

        right_layout.addWidget(self.play_menu)

        content_layout.addLayout(right_layout)
        main_layout.addLayout(content_layout)

        # ================== CONNECT MENU -> STACK ==================
        self.menu_tabs.page_changed.connect(self.stack.switch_to)

        # ================== CONNECT HOME -> PLAYLIST PAGE ==================
        self.stack.home_page.playlist_opened.connect(self._open_playlist)

        # ================== GLOBAL STYLE ==================
        self.setStyleSheet("""
            QWidget#central {
                background: transparent;
            }
            QWidget {
                background: transparent;
            }
        """)

    # ================== OPEN PLAYLIST ==================
    @asyncSlot(object)
    async def _open_playlist(self, playlist) -> None:
        await self.stack.open_playlist(playlist)

    # ================== RESIZE ==================
    def resizeEvent(self, event) -> None:
        self.background.resize(self.size())
        self.dark_overlay.resize(self.size())

        # visualizer: full width, centered vertically
        viz_h = self.visualizer.height()
        self.visualizer.setGeometry(
            0,
            (self.height() - viz_h) // 2,
            self.width(),
            viz_h,
        )

        super().resizeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NeonMusic()
    window.show()

    sys.exit(app.exec())
