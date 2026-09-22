from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.ui import resources
from quantis.ui.views.widgets.brand_mark import BrandMark


class AppHeader(QFrame):
    """Шапка: бренд QUANTIS + заголовок страницы + chrome окна."""

    hide_ui_requested = Signal()
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("appHeader")
        self.setFixedHeight(52)
        self._drag_offset: QPoint | None = None
        self._maximized = False

        row = QHBoxLayout(self)
        row.setContentsMargins(16, 0, 0, 0)
        row.setSpacing(12)

        self._brand = BrandMark()
        row.addWidget(self._brand, 0, Qt.AlignmentFlag.AlignVCenter)

        self._wordmark = QLabel("QUANTIS")
        self._wordmark.setObjectName("headerBrandWordmark")
        row.addWidget(self._wordmark, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        text_col.setContentsMargins(8, 0, 0, 0)

        self._title = QLabel("Главная")
        self._title.setObjectName("headerGreeting")
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("headerSub")
        self._subtitle.setVisible(False)

        text_col.addWidget(self._title)
        text_col.addWidget(self._subtitle)
        row.addLayout(text_col, stretch=1)

        controls = QHBoxLayout()
        controls.setSpacing(0)
        controls.setContentsMargins(0, 0, 0, 0)

        self._hide_ui_btn = self._make_control(
            "windowHideUiBtn",
            resources.icon_path("hide-ui.svg"),
            "Скрыть интерфейс (S)",
            self.hide_ui_requested.emit,
        )
        self._min_btn = self._make_control(
            "windowMinBtn",
            resources.icon_path("minimize.svg"),
            "Свернуть",
            self.minimize_requested.emit,
        )
        self._max_btn = self._make_control(
            "windowMaxBtn",
            resources.icon_path("maximize.svg"),
            "Развернуть",
            self.maximize_requested.emit,
        )
        self._close_btn = self._make_control(
            "windowCloseBtn",
            resources.icon_path("close.svg"),
            "Закрыть",
            self.close_requested.emit,
        )

        controls.addWidget(self._hide_ui_btn)
        controls.addWidget(self._min_btn)
        controls.addWidget(self._max_btn)
        controls.addWidget(self._close_btn)
        row.addLayout(controls)

    def _make_control(
        self,
        object_name: str,
        icon_path: str,
        tooltip: str,
        on_click,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setIcon(QIcon(icon_path))
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(True)
        button.setFixedSize(46, 36)
        button.clicked.connect(on_click)
        return button

    def set_page(self, title: str, subtitle: str = "") -> None:
        self._title.setText(title)
        if subtitle:
            self._subtitle.setText(subtitle)
            self._subtitle.setVisible(True)
        else:
            self._subtitle.setVisible(False)

    def set_maximized(self, maximized: bool) -> None:
        self._maximized = maximized
        icon_name = "restore.svg" if maximized else "maximize.svg"
        tooltip = "Восстановить" if maximized else "Развернуть"
        self._max_btn.setIcon(QIcon(resources.icon_path(icon_name)))
        self._max_btn.setToolTip(tooltip)

    def _can_drag(self, pos: QPoint) -> bool:
        widget = self.childAt(pos)
        while widget is not None and widget is not self:
            if isinstance(widget, QToolButton):
                return False
            widget = widget.parentWidget()
        return True

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._can_drag(
            event.position().toPoint()
        ):
            window = self.window()
            if window is not None and not window.isMaximized():
                if self._start_system_move(window):
                    event.accept()
                    return
                self._drag_offset = (
                    event.globalPosition().toPoint() - window.frameGeometry().topLeft()
                )
                event.accept()
                return
        super().mousePressEvent(event)

    @staticmethod
    def _start_system_move(window: QWidget) -> bool:
        """Перенос окна силами оконного менеджера (на Wayland move() не работает)."""
        handle = window.windowHandle()
        return bool(handle is not None and handle.startSystemMove())

    def mouseMoveEvent(self, event) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._drag_offset is not None
        ):
            window = self.window()
            if window is not None and not window.isMaximized():
                window.move(event.globalPosition().toPoint() - self._drag_offset)
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._can_drag(
            event.position().toPoint()
        ):
            self.maximize_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
