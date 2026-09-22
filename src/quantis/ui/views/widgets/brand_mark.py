from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from quantis.ui import resources


class BrandMark(QLabel):
    """Компактный логотип Quantis из assets/icons/logo.png."""

    SIZE = 36

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerBrandMark")
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setScaledContents(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = QPixmap(resources.icon_path("logo.png"))
        if not pixmap.isNull():
            self.setPixmap(
                pixmap.scaled(
                    self.SIZE,
                    self.SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.setText("Q")
