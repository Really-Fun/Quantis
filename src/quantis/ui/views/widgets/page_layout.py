"""Общая раскладка страниц: одни отступы и один заголовок на всех.

Раньше каждая страница задавала свои поля (16, 24, 28 px) и оборачивала
содержимое в стеклянную панель — край контента прыгал от страницы к
странице, а внутри панели лежали ещё карточки. Теперь страница — это поля
отсюда и заголовок ``PageTitle``; рамка остаётся только у того, что
действительно является отдельным объектом (карточка аккаунта, плагина).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from quantis.ui import resources
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor

PAGE_MARGINS = (16, 16, 28, 32)
"""Слева, сверху, справа, снизу. Слева меньше: отступ даёт меню."""
PAGE_SPACING = 28
"""Между блоками страницы."""
CONTENT_MAX_W = 880
"""Ширина колонки у страниц-форм (настройки, аккаунты): длинные строки
на широком окне читать неудобно."""


def apply_page_margins(layout: QBoxLayout, *, spacing: int = PAGE_SPACING) -> None:
    layout.setContentsMargins(*PAGE_MARGINS)
    layout.setSpacing(spacing)


class PageTitle(QWidget):
    """Заголовок страницы: крупное название, подпись и место под кнопки справа."""

    def __init__(
        self, title: str, subtitle: str = "", parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("pageTitleBlock")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(4)
        self._title = QLabel(title)
        self._title.setObjectName("pageTitle")
        col.addWidget(self._title)
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("pageSubtitle")
        self._subtitle.setWordWrap(True)
        self._subtitle.setVisible(bool(subtitle))
        col.addWidget(self._subtitle)
        row.addLayout(col, 1)
        self._actions = QHBoxLayout()
        self._actions.setSpacing(8)
        row.addLayout(self._actions)

    def add_action(self, widget: QWidget) -> None:
        self._actions.addWidget(widget)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))


class EmptyState(QWidget):
    """Пустая страница: значок, заголовок, пояснение и (если есть) кнопка —
    вместо одной серой фразы посреди пустоты."""

    def __init__(
        self,
        icon: str,
        title: str,
        text: str,
        action: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        col = QVBoxLayout(self)
        col.setContentsMargins(24, 24, 24, 48)
        col.setSpacing(8)
        col.addStretch(1)
        self._icon_name = icon
        self._icon = QLabel()
        self._icon.setObjectName("emptyStateIcon")
        self._icon.setFixedSize(64, 64)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addSpacing(8)
        self._title = QLabel(title)
        self._title.setObjectName("emptyStateTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self._title)
        self._text = QLabel(text)
        self._text.setObjectName("emptyStateText")
        self._text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._text.setWordWrap(True)
        self._text.setFixedWidth(420)  # ширина задана — перенос считает высоту
        col.addWidget(self._text, 0, Qt.AlignmentFlag.AlignHCenter)
        self.button: QPushButton | None = None
        if action:
            col.addSpacing(10)
            self.button = QPushButton(action)
            self.button.setObjectName("searchButton")
            self.button.setCursor(Qt.CursorShape.PointingHandCursor)
            col.addWidget(self.button, 0, Qt.AlignmentFlag.AlignHCenter)
        col.addStretch(2)
        self.refresh_icon()
        UiPreferences().theme_changed.connect(self.refresh_icon)

    def refresh_icon(self) -> None:
        color = qcolor(UiPreferences().theme.colors.text_meta)
        self._icon.setPixmap(resources.load_icon(self._icon_name, color).pixmap(40, 40))

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_text(self, text: str) -> None:
        self._text.setText(text)
        self._fit_text()

    def _fit_text(self) -> None:
        # Перенос строк в QLabel layout не досчитывает по высоте — задаём
        # её сами, когда шрифт из стиля уже применён.
        self._text.ensurePolished()
        self._text.setMinimumHeight(self._text.heightForWidth(self._text.width()))

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._fit_text()
