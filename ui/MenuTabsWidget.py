from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QLabel


class MenuTabs(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.nav_layout = QVBoxLayout()

        self.main_layout.addLayout(self.nav_layout)

        self.title1 = QLabel("AFAFS")
        self.title1.setText("AAAAAA")
        self.title2 = QLabel("AAAAA")

        self.nav_layout.addWidget(self.title1)
        self.nav_layout.addWidget(self.title2)