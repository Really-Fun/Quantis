"""Страница пользователя.

Заглушка под API-данные: токены, ключи, настройки аккаунта.
"""

import keyring

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ui.theme import PANEL_RADIUS, scroll_qss


class UserPage(QWidget):
    """Страница профиля с полями для токенов и API-ключей."""

    go_back = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("UserPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        header = _UserHeader()
        header.back_clicked.connect(self.go_back.emit)
        root.addWidget(header)
        root.addSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet(scroll_qss("_user_scroll"))

        content = QWidget()
        content.setObjectName("_user_scroll")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(12)

        content_lay.addWidget(_TokenSection())
        content_lay.addWidget(_InfoSection())
        content_lay.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)


class _UserHeader(QWidget):
    back_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(
            f"""
            QWidget {{
                background: rgba(10, 14, 22, 220);
                border-radius: {PANEL_RADIUS}px;
                border: 1px solid rgba(0, 220, 255, 35);
            }}
            """
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 0, 20, 0)

        back = QToolButton()
        back.setText("←")
        back.setFixedSize(36, 36)
        back.setCursor(Qt.PointingHandCursor)
        back.setStyleSheet(
            """
            QToolButton {
                color: white;
                font-size: 18px;
                font-weight: 700;
                background: rgba(0, 0, 0, 100);
                border-radius: 18px;
                border: none;
            }
            QToolButton:hover { background: rgba(0, 220, 255, 60); }
            """
        )
        back.clicked.connect(self.back_clicked.emit)
        lay.addWidget(back)
        lay.addSpacing(12)

        title = QLabel("Профиль")
        title.setStyleSheet(
            "color: #fff; font-size: 24px; font-weight: 800; background: transparent;"
        )
        lay.addWidget(title)
        lay.addStretch()


class _TokenSection(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: rgba(12, 14, 20, 210); border-radius: {PANEL_RADIUS}px; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)

        title = QLabel("API-данные (заглушка)")
        title.setStyleSheet("color: #fff; font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        self.yandex_token = QLineEdit()
        self.yandex_token.setPlaceholderText("Yandex token")
        self.yandex_token.setEchoMode(QLineEdit.Password)

        self.youtube_key = QLineEdit()
        self.youtube_key.setPlaceholderText("YouTube API key")
        self.youtube_key.setEchoMode(QLineEdit.Password)

        custom_api = QLineEdit()
        custom_api.setPlaceholderText("Другой API key / secret")
        custom_api.setEchoMode(QLineEdit.Password)

        field_qss = (
            "QLineEdit {"
            "color: #fff; background: rgba(255,255,255,10);"
            "border: 1px solid rgba(255,255,255,25); border-radius: 8px; padding: 8px;"
            "}"
            "QLineEdit:focus { border: 1px solid rgba(0,220,255,110); }"
        )
        self.yandex_token.setStyleSheet(field_qss)
        self.youtube_key.setStyleSheet(field_qss)
        custom_api.setStyleSheet(field_qss)

        lay.addWidget(self.yandex_token)
        lay.addWidget(self.youtube_key)

        lay.addWidget(custom_api)

        save_btn = QPushButton("Сохранить")
        # save_btn.setCursor(Qt.ForbiddenCursor)
        save_btn.setStyleSheet(
            "QPushButton {"
            "color: rgba(255,255,255,120); background: rgba(255,255,255,10);"
            "border: 1px solid rgba(255,255,255,20); border-radius: 10px; padding: 8px 10px;"
            "}"
        )
        save_btn.clicked.connect(self.save_apis)
        lay.addWidget(save_btn)

    def get_apis(self):
        yandex_api = self.yandex_token.text().strip()
        return {"YANDEX_TOKEN_NEON_APP": yandex_api}

    def is_correct(self, apis: dict) -> bool:
        return True

    def write_apis(self, apis: dict) -> bool:
        for key in apis:
            keyring.set_password(key, "NEON_APP", apis[key])

    def save_apis(self, text: str):
        apis = self.get_apis()
        if self.is_correct(apis):
            self.write_apis(apis)
        else:
            print("Некорректные апи")


class _InfoSection(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: rgba(12, 14, 20, 210); border-radius: {PANEL_RADIUS}px; }}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(6)

        title = QLabel("Что будет здесь дальше")
        title.setStyleSheet("color: #fff; font-size: 16px; font-weight: 700;")
        lay.addWidget(title)

        info = QLabel(
            "Пока это заглушка.\n"
            "Планируется хранение и управление токенами, API-ключами,\n"
            "а также базовыми настройками аккаунта."
        )
        info.setStyleSheet("color: rgba(255,255,255,180); font-size: 13px;")
        info.setWordWrap(True)
        lay.addWidget(info)
