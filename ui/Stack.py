from PySide6.QtWidgets import QWidget, QStackedWidget, QVBoxLayout

from ui.HomePage import HomePage
from ui.SearchPage import SearchPage

class Stack(QWidget):

    def __init__(self, parent=None):
        super().__init__()

        self.stack = QStackedWidget()
        self.layout = QVBoxLayout(self)

        self.home_page = HomePage()
        self.search_page = SearchPage()

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.search_page)

        self.stack.setCurrentWidget(self.home_page)

        self.layout.addWidget(self.stack)