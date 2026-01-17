from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QLabel, QPushButton


class MenuTabs(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.main_layout = QVBoxLayout(self)
        self.nav_layout = QVBoxLayout()

        self.main_layout.addLayout(self.nav_layout)

        self.pixmap = QPixmap("assets/icons/testneonmusic.png")
        icon = QIcon(self.pixmap)

        self.main_nav = QPushButton()
        self.main_nav.setIcon(icon)
        self.main_nav.setIconSize(QSize(125, 125))
        self.main_nav.setFixedSize(125, 125)# Размер иконки под логотип

        self.main_nav.clicked.connect(self.some_test)
        self.main_nav.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0);
                border: none;
                padding: 0;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 10);
            }
        """)
        self.main_nav.setAttribute(Qt.WA_TranslucentBackground, True)
        self.title1 = QLabel("AFAFS")
        self.title2 = QLabel("AAAAA")

        self.nav_layout.addWidget(self.main_nav)
        self.nav_layout.addWidget(self.title1)
        self.nav_layout.addWidget(self.title2)


    def some_test(self):
        print("TEST")