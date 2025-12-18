"""Главная страница"""
import sys

from PySide6.QtWidgets import QMainWindow, QApplication, QVBoxLayout, QWidget

from ui.MenuPlayWidget import PlayMenu
from ui.MenuTabsWidget import MenuTabs


class NeonMusic(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeonMusic ♪♪♪")
        self.setBaseSize(600, 800)
        self.setMaximumHeight(1080)
        self.setMaximumWidth(1920)

        central = QWidget()
        self.main_layout = QVBoxLayout(central)
        self.main_layout.addWidget(MenuTabs(central))
        self.main_layout.addStretch()
        self.main_layout.addWidget(PlayMenu(central))

        self.setCentralWidget(central)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NeonMusic()
    window.show()

    sys.exit(app.exec())