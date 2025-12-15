"""Главная страница"""
import sys

from PySide6.QtWidgets import QMainWindow, QApplication, QVBoxLayout

from ui.MenuPlayWidget import PlayMenu


class NeonMusic(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NeonMusic ♪♪♪")
        self.setBaseSize(600, 800)
        self.setMaximumHeight(1080)
        self.setMaximumWidth(1920)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.addWidget(PlayMenu(self))

if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NeonMusic()
    window.show()

    sys.exit(app.exec())