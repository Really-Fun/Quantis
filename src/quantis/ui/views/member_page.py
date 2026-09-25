"""Страница Member: подписки и токены/cookies сервисов."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from quantis.config.credentials import (
    delete_yandex_token,
    save_yandex_token,
    save_youtube_cookie,
    yandex_token,
    yotube_cookie,
)
from quantis.core.async_bridge import AsyncBridge
from quantis.services.membership import MembershipSnapshot, fetch_membership_snapshot
from quantis.ui.views.widgets.glass_panel import GlassPanel

_ERROR_PREVIEW_CHARS = 140


def _short_error(error: str) -> str:
    """Первая строка ошибки без простыни JSON; целиком она в подсказке."""
    first = error.strip().splitlines()[0] if error.strip() else ""
    if len(first) > _ERROR_PREVIEW_CHARS:
        first = first[:_ERROR_PREVIEW_CHARS].rstrip() + "…"
    return first


class MemberPage(QWidget):
    def __init__(
        self,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._loading = False
        self.setObjectName("settingsPage")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 8, 16, 20)
        layout.setSpacing(12)

        panel = GlassPanel()
        panel.setObjectName("settingsPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(22, 20, 22, 22)
        panel_layout.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(QLabel("Подписки", objectName="settingsSectionLabel"))
        header.addStretch()
        self._refresh_btn = QPushButton("Обновить")
        self._refresh_btn.setObjectName("searchButton")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh_membership)
        header.addWidget(self._refresh_btn)
        panel_layout.addLayout(header)

        yandex_info_row, yandex_info_body = self._row(
            "Yandex Music · Плюс",
            "Статус подписки на аккаунте Yandex",
        )
        self._yandex_info = QLabel("Загрузка…")
        self._yandex_info.setObjectName("settingsRowDesc")
        self._yandex_info.setWordWrap(True)
        yandex_info_body.addWidget(self._yandex_info)
        panel_layout.addWidget(yandex_info_row)

        youtube_info_row, youtube_info_body = self._row(
            "YouTube Music",
            "Авторизация через cookies браузера",
        )
        self._youtube_info = QLabel("Загрузка…")
        self._youtube_info.setObjectName("settingsRowDesc")
        self._youtube_info.setWordWrap(True)
        youtube_info_body.addWidget(self._youtube_info)
        panel_layout.addWidget(youtube_info_row)

        panel_layout.addWidget(QLabel("Доступ", objectName="settingsSectionLabel"))

        yandex_row, yandex_body = self._row(
            "Токен Yandex Music",
            "OAuth-токен хранится в системном keyring",
        )
        token_row = QHBoxLayout()
        self._yandex_token = QLineEdit()
        self._yandex_token.setObjectName("settingLineEdit")
        self._yandex_token.setPlaceholderText("Вставьте OAuth-токен")
        self._yandex_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._save_token_btn = QPushButton("Сохранить")
        self._save_token_btn.setObjectName("searchButton")
        self._save_token_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_token_btn.clicked.connect(self._on_save_yandex_token)
        self._delete_token_btn = QPushButton("Удалить")
        self._delete_token_btn.setObjectName("searchButton")
        self._delete_token_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_token_btn.clicked.connect(self._on_delete_yandex_token)
        token_row.addWidget(self._yandex_token, stretch=1)
        token_row.addWidget(self._save_token_btn)
        token_row.addWidget(self._delete_token_btn)
        yandex_body.addLayout(token_row)
        self._token_status = QLabel()
        self._token_status.setObjectName("settingsRowDesc")
        yandex_body.addWidget(self._token_status)
        panel_layout.addWidget(yandex_row)

        cookie_row, cookie_body = self._row(
            "Cookies YouTube Music",
            "Лучше: Request Headers с music.youtube.com (Network → browse). "
            "Также: JSON Cookie-Editor / Netscape. Сохраняется в credentials/youtube_cookies.txt",
        )
        self._youtube_cookie = QPlainTextEdit()
        self._youtube_cookie.setObjectName("settingLineEdit")
        self._youtube_cookie.setPlaceholderText(
            "Вставьте Request Headers с music.youtube.com\n"
            "или JSON кук Cookie-Editor / EditThisCookie (youtube.com)\n"
            "или готовый browser.json от ytmusicapi"
        )
        self._youtube_cookie.setFixedHeight(120)
        cookie_body.addWidget(self._youtube_cookie)
        hint = QLabel(
            "Куки сохраняются для YouTube Music (поиск) и yt-dlp (воспроизведение). "
            "Лучше Request Headers с music.youtube.com (Network → POST browse). "
            "Нужны SAPISID / сессия Music — иначе «Sign in to confirm you’re not a bot»."
        )
        hint.setObjectName("settingsRowDesc")
        hint.setWordWrap(True)
        cookie_body.addWidget(hint)
        cookie_actions = QHBoxLayout()
        cookie_actions.addStretch()
        self._save_cookie_btn = QPushButton("Сохранить")
        self._save_cookie_btn.setObjectName("searchButton")
        self._save_cookie_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_cookie_btn.clicked.connect(self._on_save_youtube_cookie)
        cookie_actions.addWidget(self._save_cookie_btn)
        cookie_body.addLayout(cookie_actions)
        self._cookie_status = QLabel()
        self._cookie_status.setObjectName("settingsRowDesc")
        cookie_body.addWidget(self._cookie_status)
        panel_layout.addWidget(cookie_row)

        panel_layout.addStretch()
        layout.addWidget(panel)
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._update_cred_status()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._update_cred_status()
        self.refresh_membership()

    def _row(self, title: str, desc: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("settingsRow")
        col = QVBoxLayout(frame)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(8)
        col.addWidget(QLabel(title, objectName="settingsRowTitle"))
        description = QLabel(desc, objectName="settingsRowDesc")
        description.setWordWrap(True)
        col.addWidget(description)
        return frame, col

    def _update_cred_status(self) -> None:
        if yandex_token():
            self._token_status.setText("Токен сохранён")
        else:
            self._token_status.setText("Без токена поиск Yandex недоступен")
        if yotube_cookie():
            self._cookie_status.setText("Cookies сохранены")
        else:
            self._cookie_status.setText(
                "Без cookies — ограниченный доступ к YouTube Music"
            )

    def refresh_membership(self) -> None:
        if self._bridge is None or self._loading:
            return
        self._loading = True
        self._refresh_btn.setEnabled(False)
        self._yandex_info.setText("Загрузка…")
        self._youtube_info.setText("Загрузка…")
        self._bridge.schedule(self._load_membership())

    async def _load_membership(self) -> None:
        try:
            snapshot = await fetch_membership_snapshot()
        except Exception as exc:
            message = str(exc)
            if self._bridge is not None:
                self._bridge.invoke_main(lambda: self._on_membership_failed(message))
            return
        if self._bridge is not None:
            self._bridge.invoke_main(lambda: self._apply_membership(snapshot))

    def _on_membership_failed(self, message: str) -> None:
        self._loading = False
        self._refresh_btn.setEnabled(True)
        self._yandex_info.setText(f"Ошибка: {message}")
        self._youtube_info.setText(f"Ошибка: {message}")

    def _apply_membership(self, snapshot: MembershipSnapshot) -> None:
        self._loading = False
        self._refresh_btn.setEnabled(True)

        ya = snapshot.yandex
        ya_lines: list[str] = []
        if ya.display_name:
            ya_lines.append(f"Аккаунт: {ya.display_name}")
        ya_lines.append(ya.detail or "Нет данных")
        if ya.has_plus and ya.plus_until:
            ya_lines.append(f"Действует до: {ya.plus_until}")
        if ya.error:
            ya_lines.append(f"Детали: {_short_error(ya.error)}")
        self._yandex_info.setText("\n".join(ya_lines))
        self._yandex_info.setToolTip(ya.error or "")

        yt = snapshot.youtube
        yt_lines: list[str] = []
        if yt.account_name:
            yt_lines.append(f"Аккаунт: {yt.account_name}")
        if yt.channel_handle:
            yt_lines.append(f"Канал: {yt.channel_handle}")
        yt_lines.append(yt.detail or "Нет данных")
        if yt.error:
            yt_lines.append(f"Детали: {_short_error(yt.error)}")
        self._youtube_info.setText("\n".join(yt_lines))
        self._youtube_info.setToolTip(yt.error or "")

    def _on_save_yandex_token(self) -> None:
        try:
            save_yandex_token(self._yandex_token.text())
            self._yandex_token.clear()
            self._token_status.setText("Токен сохранён")
            self.refresh_membership()
        except ValueError as exc:
            self._token_status.setText(str(exc))
        except Exception as exc:
            self._token_status.setText(f"Ошибка: {exc}")

    def _on_delete_yandex_token(self) -> None:
        try:
            delete_yandex_token()
            self._yandex_token.clear()
            self._token_status.setText(
                "Токен удалён с этого компьютера. "
                "На Яндексе он ещё жив — отзовите доступ в id.yandex.ru"
            )
            self.refresh_membership()
        except Exception as exc:
            self._token_status.setText(f"Ошибка: {exc}")

    def _on_save_youtube_cookie(self) -> None:
        try:
            save_youtube_cookie(self._youtube_cookie.toPlainText())
            self._youtube_cookie.clear()
            self._cookie_status.setText("Cookies сохранены")
            self.refresh_membership()
        except ValueError as exc:
            self._cookie_status.setText(str(exc))
        except Exception as exc:
            message = str(exc)
            if "CredWrite" in message or "1783" in message:
                message = (
                    "Не удалось сохранить cookies. "
                    "Попробуйте ещё раз — они пишутся в файл, не в keyring."
                )
            self._cookie_status.setText(f"Ошибка: {message}")
