from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget


class HomeSection(QWidget):
    """Секция главной: заголовок в стиле «shelf» + контент."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("homeSection")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)
        header.setContentsMargins(0, 0, 0, 0)

        text = QVBoxLayout()
        text.setSpacing(2)
        self._title = QLabel(title)
        self._title.setObjectName("homeSectionTitle")
        text.addWidget(self._title)
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("homeSectionSubtitle")
        self._subtitle.setVisible(bool(subtitle))
        text.addWidget(self._subtitle)
        header.addLayout(text, stretch=1)

        self._badge = QLabel()
        self._badge.setObjectName("homeSectionBadge")
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._badge.hide()
        header.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignTop)

        self._actions = QHBoxLayout()
        self._actions.setContentsMargins(0, 0, 0, 0)
        self._actions.setSpacing(6)
        header.addLayout(self._actions)

        root.addLayout(header)

        self._body = QWidget()
        self._body.setObjectName("homeSectionBody")
        self._body.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        root.addWidget(self._body, stretch=1)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def set_badge(self, text: str) -> None:
        if text:
            self._badge.setText(text)
            self._badge.show()
        else:
            self._badge.hide()

    def set_header_action(self, widget: QWidget | None) -> None:
        while self._actions.count():
            item = self._actions.takeAt(0)
            old = item.widget()
            if old is not None:
                old.deleteLater()
        if widget is not None:
            self._actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignTop)

    def add_widget_block(self, widget: QWidget, *, expand: bool = False) -> None:
        while self._body_layout.count():
            item = self._body_layout.takeAt(0)
            old = item.widget()
            if old is not None:
                old.deleteLater()
        vertical = (
            QSizePolicy.Policy.Expanding if expand else QSizePolicy.Policy.Maximum
        )
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, vertical)
        if expand:
            self.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            self._body.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
        self._body_layout.addWidget(widget, stretch=1 if expand else 0)
