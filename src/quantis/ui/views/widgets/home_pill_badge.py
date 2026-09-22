"""Компактный pill-бейдж для главной (волна, продолжить, счётчики)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy


class HomePillBadge(QLabel):
    """Небольшая метка — без кричащего градиента."""

    def __init__(
        self,
        text: str,
        *,
        variant: str = "default",
        parent=None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("homePillBadge")
        self.setProperty("variant", variant)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_variant(self, variant: str) -> None:
        self.setProperty("variant", variant)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
