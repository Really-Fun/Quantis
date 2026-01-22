from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel


class SearchPage(QWidget):

    def __init__(self, parent=None):
        super().__init__()

        self.setObjectName("SearchPage")

        self.main_layout = QVBoxLayout(self)

        self.main_label = QLabel("Поиск")
        self.main_label.setObjectName("Header")

        self.main_layout.addWidget(self.main_label)
        self.main_layout.addStretch()

