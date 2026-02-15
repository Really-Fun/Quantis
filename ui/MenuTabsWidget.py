import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QPushButton,
    QFrame, QToolButton, QHBoxLayout,
)
from PySide6.QtGui import QIcon, QDesktopServices
from PySide6.QtCore import QUrl


class MenuTabs(QWidget):
    """Левая панель навигации. Сигнал ``page_changed(int)`` при клике."""

    page_changed = Signal(int)

    # Индексы страниц (должны совпадать со Stack)
    HOME = 0
    SEARCH = 1
    LIBRARY = 2
    SETTINGS = 3
    USER = 4

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedWidth(150)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # ================= ПАНЕЛЬ =================
        panel = QFrame(self)
        panel.setObjectName("navPanel")

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(8, 10, 8, 10)
        panel_layout.setSpacing(6)
        panel_layout.setAlignment(Qt.AlignTop)

        # --- кнопки навигации ---
        self.btn_home = self._make_nav_button("🏠")
        self.btn_search = self._make_nav_button("🔍")
        self.btn_library = self._make_nav_button("🎵")

        self.btn_home.setChecked(True)

        self.btn_home.clicked.connect(lambda: self._switch(self.HOME))
        self.btn_search.clicked.connect(lambda: self._switch(self.SEARCH))
        self.btn_library.clicked.connect(lambda: self._switch(self.LIBRARY))

        panel_layout.addWidget(self.btn_home)
        panel_layout.addWidget(self.btn_search)
        panel_layout.addWidget(self.btn_library)

        # --- нижние кнопки инструментов ---
        self.btn_settings = self._make_tool_button("assets/icons/setting.png")
        self.btn_settings.clicked.connect(lambda: self._switch(self.SETTINGS))
        self.btn_folder = self._make_tool_button("assets/icons/folder.png")
        self.btn_folder.clicked.connect(self._open_app_folder)
        self.btn_account = self._make_tool_button("assets/icons/account.png")
        self.btn_account.clicked.connect(lambda: self._switch(self.USER))

        panel_layout.addStretch(1)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(self.btn_settings)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_folder)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_account)
        panel_layout.addLayout(bottom_layout)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(panel)

        self._nav_buttons = [self.btn_home, self.btn_search, self.btn_library]

        # ================= СТИЛИ =================
        self.setStyleSheet("""
            QFrame#navPanel {
                background: rgba(0, 0, 0, 160);
                border-right: 1px solid rgba(0, 255, 255, 120);
            }

            QPushButton#navButton {
                color: #e6ffff;
                font-size: 16px;
                border-radius: 10px;
                background: transparent;
            }

            QPushButton#navButton:hover {
                background: rgba(0, 255, 255, 70);
            }

            QPushButton#navButton:pressed {
                background: rgba(0, 255, 255, 140);
            }

            QPushButton#navButton:checked {
                background: rgba(0, 255, 255, 160);
                color: white;
            }

            QToolButton#roundButton,
            QToolButton#roundButton:hover,
            QToolButton#roundButton:pressed,
            QToolButton#roundButton:checked {
                background-color: rgba(0, 0, 0, 120);
                border: none;
                outline: none;
            }
        """)

    # --- переключение ---

    def _switch(self, index: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
        self.page_changed.emit(index)

    # --- фабрики виджетов ---

    @staticmethod
    def _make_nav_button(text: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setObjectName("navButton")
        btn.setCheckable(True)
        return btn

    @staticmethod
    def _make_tool_button(icon_path: str, size: int = 32) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(QIcon(icon_path))
        btn.setIconSize(QSize(size - 4, size - 4))
        btn.setFixedSize(size, size)
        btn.setAutoRaise(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setObjectName("roundButton")
        return btn

    @staticmethod
    def _open_app_folder() -> None:
        """Открывает папку приложения (рядом с music/covers/assets)."""
        if getattr(sys, "frozen", False):
            app_dir = Path(sys.executable).resolve().parent
        else:
            app_dir = Path(__file__).resolve().parent.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_dir)))
