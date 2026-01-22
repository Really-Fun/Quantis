"""Главная страница"""
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


from ui.MenuPlayWidget import PlayMenu
from ui.MenuTabsWidget import MenuTabs
from ui.Stack import Stack

class NeonMusic(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("NeonMusic ♪♪♪")
        self.resize(600, 800)
        self.setMaximumSize(1920, 1080)

        # ================== CENTRAL ==================
        central = QWidget(self)
        central.setObjectName("central")
        self.setCentralWidget(central)

        # ================== BACKGROUND ==================
        self.background = QLabel(central)
        self.background.setPixmap(QPixmap("assets/background/real.jpg"))
        self.background.setScaledContents(True)
        self.background.lower()  # фон под всеми виджетами

        # ================== DARK OVERLAY ==================
        self.dark_overlay = QFrame(central)
        self.dark_overlay.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 150);  /* 0–255 */
            }
        """)
        self.dark_overlay.lower()
        self.background.lower()

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
        right_layout.addWidget(self.stack)

        # тут будет основной контент
        right_layout.addStretch(1)

        # -------- PLAY MENU (BOTTOM) --------
        self.play_menu = PlayMenu()
        self.play_menu.setFixedHeight(90)
        self.play_menu.setAttribute(Qt.WA_TranslucentBackground)

        right_layout.addWidget(self.play_menu)

        content_layout.addLayout(right_layout)
        main_layout.addLayout(content_layout)

        # ================== GLOBAL STYLE ==================
        self.setStyleSheet("""
            QWidget#central {
                background: transparent;
            }
            QWidget {
                background: transparent;
            }
        """)

    # ================== RESIZE BACKGROUND ==================
    def resizeEvent(self, event):
        self.background.resize(self.size())
        self.dark_overlay.resize(self.size())
        super().resizeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NeonMusic()
    window.show()

    sys.exit(app.exec())
