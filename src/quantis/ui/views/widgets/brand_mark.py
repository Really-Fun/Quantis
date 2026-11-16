from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QWidget

from quantis.ui import resources


class BrandMark(QLabel):
    """Векторный знак Quantis для узкой боковой панели."""

    SIZE = 44

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sideBrandMark")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAccessibleName("Quantis")
        self.tint(QColor("#B4BCC8"))

    def tint(self, color: QColor) -> None:
        self.setPixmap(resources.load_icon("brand-mark.svg", color).pixmap(40, 40))
