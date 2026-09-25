from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.ui import resources
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor
from quantis.ui.views.widgets.brand_mark import BrandMark


class AppHeader(QFrame):
    """Шапка: бренд QUANTIS + заголовок страницы + chrome окна."""

    hide_ui_requested = Signal()
    backdrop_requested = Signal()
    """Кнопка «Фон» — открыть/закрыть панель фона."""
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

        self._backdrop_btn = self._make_control(
            "windowBackdropBtn",
            "backdrop.svg",
            "Фон",
            self.backdrop_requested.emit,
        )
        self._hide_ui_btn = self._make_control(
            "windowHideUiBtn",
            "hide-ui.svg",
            "Скрыть интерфейс (S)",
            self.hide_ui_requested.emit,
        )
        self._min_btn = self._make_control(
            "windowMinBtn",
            "minimize.svg",
            "Свернуть",
            self.minimize_requested.emit,
        )
        self._max_btn = self._make_control(
            "windowMaxBtn",
            "maximize.svg",
            "Развернуть",
            self.maximize_requested.emit,
        )
        self._close_btn = self._make_control(
            "windowCloseBtn",
            "close.svg",
            "Закрыть",
            self.close_requested.emit,
        )

        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self._refresh_icons)
        self._refresh_icons()

        controls.addWidget(self._backdrop_btn)
        controls.addWidget(self._hide_ui_btn)
        controls.addWidget(self._min_btn)
        controls.addWidget(self._max_btn)
        controls.addWidget(self._close_btn)
        row.addLayout(controls)

    def _make_control(
        self,
        object_name: str,
        icon_name: str,
        tooltip: str,
        on_click,
    ) -> QToolButton:
        button = QToolButton(self)
        button.setObjectName(object_name)
        button.setProperty("iconName", icon_name)
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAutoRaise(True)
        button.setFixedSize(46, 36)
        button.clicked.connect(on_click)
        return button

    def _refresh_icons(self) -> None:
        """Значки кнопок окна цветом ``text_soft`` темы (в SVG — светло-серый)."""
        color = qcolor(self._prefs.theme.colors.text_soft)
        for button in (
            self._backdrop_btn,
            self._hide_ui_btn,
            self._min_btn,
            self._max_btn,
            self._close_btn,
        ):
            button.setIcon(resources.load_icon(button.property("iconName"), color))

    @property
    def backdrop_button(self) -> QToolButton:
        """Якорь панели «Фон»."""
        return self._backdrop_btn

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
        self._max_btn.setProperty("iconName", icon_name)
        self._max_btn.setToolTip(tooltip)
        self._refresh_icons()

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
