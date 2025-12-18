from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QLabel, QPushButton


class MenuTabs(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.nav_layout = QVBoxLayout()

        self.main_layout.addLayout(self.nav_layout)

        self.main_nav = QPushButton()
        self.main_nav.setIcon(QIcon("assets/icons/ico.png"))
        self.title1 = QLabel("AFAFS")
        self.title2 = QLabel("AAAAA")

        self.nav_layout.addWidget(self.main_nav)
        self.nav_layout.addWidget(self.title1)
        self.nav_layout.addWidget(self.title2)