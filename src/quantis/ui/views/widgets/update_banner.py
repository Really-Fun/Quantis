"""Плашка «доступна новая версия» под шапкой окна."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class UpdateBanner(QFrame):
    open_requested = Signal()
    dismiss_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.setVisible(False)

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 8, 12, 8)
        row.setSpacing(10)

        self._label = QLabel()
        self._label.setObjectName("updateBannerText")
        self._label.setWordWrap(True)
        row.addWidget(self._label, stretch=1)

        self._open_btn = QPushButton("Открыть релиз")
        self._open_btn.setObjectName("updateBannerButton")
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self.open_requested.emit)
        row.addWidget(self._open_btn)

        self._later_btn = QPushButton("Позже")
        self._later_btn.setObjectName("updateBannerButton")
        self._later_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._later_btn.clicked.connect(self.dismiss_requested.emit)
        row.addWidget(self._later_btn)

    def show_version(self, version: str) -> None:
        self._label.setText(f"Доступна Quantis {version}")
        self.setVisible(True)
