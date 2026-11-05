"""Страница «Аккаунты»: что подключено, что это даёт, как подключить.

Одна карточка на сервис: статус-чип, аккаунт, что даёт подключение, поле для
токена или кук и короткая инструкция. Ошибки — человеческим текстом рядом с
полем; технические подробности остаются в логе.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.config.credentials import (
    delete_yandex_token,
    delete_youtube_cookie,
    save_yandex_token,
    save_youtube_cookie,
    yandex_token,
    yotube_cookie,
)
from quantis.core.async_bridge import AsyncBridge
from quantis.services.membership import (
    AccountState,
    AccountStatus,
    MembershipSnapshot,
    fetch_membership_snapshot,
)
from quantis.ui.views.widgets.page_layout import (
    CONTENT_MAX_W,
    PageTitle,
    apply_page_margins,
)

logger = logging.getLogger(__name__)

YANDEX_TOKEN_URL = (
    "https://oauth.yandex.ru/authorize?response_type=token"
    "&client_id=23cabbbdc6cd418abb4b39c32c41195d"
)

_LIST = "<ol style='margin:0; -qt-list-indent:1'>"

_YANDEX_GUIDE = (
    _LIST + f"<li>Открой <a href='{YANDEX_TOKEN_URL}'>страницу входа Яндекса</a> "
    "и войди в аккаунт с Плюсом.</li>"
    "<li>После входа браузер перейдёт на новый адрес. Скопируй из адресной "
    "строки всё, что стоит после <b>access_token=</b> и до <b>&amp;</b>.</li>"
    "<li>Вставь это в поле выше и нажми «Сохранить».</li>"
    "</ol>"
    "<p style='margin-top:8px'>Токен хранится в системном хранилище паролей "
    "этого компьютера.</p>"
)

_YOUTUBE_GUIDE = (
    _LIST + "<li>Открой <a href='https://music.youtube.com'>music.youtube.com</a> "
    "в браузере, где ты вошёл в аккаунт.</li>"
    "<li>Нажми F12 → вкладка <b>Network</b>, в фильтре напиши <b>youtubei</b>."
    "</li>"
    "<li>На странице YouTube Music открой «Библиотеку» или «Главную» — появятся "
    "запросы <b>browse</b>, <b>next</b>, <b>guide</b>. Подойдёт любой.</li>"
    "<li>Правой кнопкой по запросу → <b>Copy</b> → <b>Copy request headers</b> "
    "и вставь в поле выше.</li>"
    "</ol>"
    "<p style='margin-top:8px'>Подойдёт и экспорт кук из расширения "
    "Cookie-Editor (JSON) или файл cookies.txt. Куки устаревают — если "
    "статус стал «Сессия истекла», повтори эти шаги.</p>"
)


def _link_color() -> str:
    """Цвет ссылок под тему: синий по умолчанию на тёмном фоне не читается."""
    from quantis.ui.preferences import UiPreferences

    try:
        return f"rgb({UiPreferences().theme.colors.hl_rgb})"
    except Exception:
        return "#4FC3F7"


def _with_links(html: str) -> str:
    color = _link_color()
    return html.replace(
        "<a href=", f"<a style='color:{color}; text-decoration:none' href="
    )


def _repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def _set_state(widget: QWidget, state: str) -> None:
    if widget.property("state") != state:
        widget.setProperty("state", state)
        _repolish(widget)


def _label(text: str, name: str, *, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


def _button(text: str, name: str, slot: Callable[[], None]) -> QPushButton:
    button = QPushButton(text)
    button.setObjectName(name)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.clicked.connect(slot)
    return button


class _Guide(QWidget):
    """Свёрнутая инструкция «Как получить…»: раскрывается по клику."""

    def __init__(self, title: str, html: str, parent: QWidget | None = None):
        super().__init__(parent)
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        self._title = title
        self._html = html
        self._toggle = QToolButton()
        self._toggle.setObjectName("memberGuideToggle")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setCheckable(True)
        self._toggle.toggled.connect(self._on_toggled)
        self._body = _label(_with_links(html), "memberGuide", wrap=True)
        self._body.setTextFormat(Qt.TextFormat.RichText)
        self._body.setOpenExternalLinks(True)
        self._body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self._body.setVisible(False)
        col.addWidget(self._toggle, alignment=Qt.AlignmentFlag.AlignLeft)
        col.addWidget(self._body)
        self._on_toggled(False)

    def _on_toggled(self, opened: bool) -> None:
        self._toggle.setText(("▾  " if opened else "▸  ") + self._title)
        if opened:
            self._body.setText(_with_links(self._html))  # тему могли сменить
        self._body.setVisible(opened)


class _ServiceCard(QFrame):
    """Карточка сервиса: шапка со статусом, аккаунт, пояснение, доступ."""

    def __init__(self, source: str, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("memberCard")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(22, 20, 22, 20)
        self.body.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(10)
        dot = QLabel()
        dot.setObjectName("memberDot")
        dot.setProperty("source", source)
        head.addWidget(dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        head.addWidget(_label(title, "memberService"))
        head.addStretch()
        self.chip = _label("Проверяем…", "memberChip")
        self.chip.setProperty("state", "checking")
        head.addWidget(self.chip, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.body.addLayout(head)

        self.account = _label("", "memberAccount")
        self.account.setVisible(False)
        self.body.addWidget(self.account)
        self.detail = _label("", "memberDetail", wrap=True)
        self.body.addWidget(self.detail)

        divider = QFrame()
        divider.setObjectName("memberDivider")
        self.body.addSpacing(4)
        self.body.addWidget(divider)
        self.body.addSpacing(2)

    def show_checking(self) -> None:
        self.chip.setText("Проверяем…")
        _set_state(self.chip, "checking")

    def show_status(self, status: AccountStatus) -> None:
        self.chip.setText(status.headline)
        _set_state(self.chip, status.state.value)
        self.account.setText(status.account or "")
        self.account.setVisible(bool(status.account))
        self.detail.setText(status.detail)


class MemberPage(QWidget):
    def __init__(
        self,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._loading = False
        self._snapshot: MembershipSnapshot | None = None
        self._yandex_editing = False
        self._youtube_editing = False
        self.setObjectName("settingsPage")

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("settingsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        apply_page_margins(layout, spacing=0)

        # Карточки сервисов прямо на странице, без общей панели вокруг.
        panel = QWidget()
        panel.setObjectName("settingsPanel")
        panel.setMaximumWidth(CONTENT_MAX_W)
        col = QVBoxLayout(panel)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(16)

        head = PageTitle(
            "Аккаунты",
            "От них зависят поиск, «Моя волна» и полные треки. "
            "Данные для входа остаются на этом компьютере.",
        )
        self._refresh_btn = _button(
            "Проверить", "settingsButton", self.refresh_membership
        )
        self._refresh_btn.setToolTip("Заново спросить у сервисов статус аккаунтов")
        head.add_action(self._refresh_btn)
        col.addWidget(head)
        col.addSpacing(8)

        self._yandex = _ServiceCard("yandex", "Яндекс Музыка")
        self._build_yandex_access(self._yandex.body)
        col.addWidget(self._yandex)

        self._youtube = _ServiceCard("youtube", "YouTube Music")
        self._build_youtube_access(self._youtube.body)
        col.addWidget(self._youtube)

        col.addStretch()
        layout.addWidget(panel)  # макс. ширина — прижат к левому краю
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._sync_access()

    # --- Яндекс -------------------------------------------------------------

    def _build_yandex_access(self, body: QVBoxLayout) -> None:
        self._yandex_saved = QWidget()
        saved = QHBoxLayout(self._yandex_saved)
        saved.setContentsMargins(0, 0, 0, 0)
        saved.setSpacing(8)
        saved.addWidget(
            _label("Токен сохранён на этом компьютере", "memberFeedback"), stretch=1
        )
        saved.addWidget(
            _button("Заменить токен", "settingsButton", self._edit_yandex_token)
        )
        saved.addWidget(
            _button("Отключить", "memberDanger", self._on_delete_yandex_token)
        )
        body.addWidget(self._yandex_saved)

        self._yandex_editor = QWidget()
        editor = QVBoxLayout(self._yandex_editor)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(6)
        editor.addWidget(_label("OAuth-токен Яндекса", "memberFieldLabel"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self._yandex_token = QLineEdit()
        self._yandex_token.setObjectName("settingLineEdit")
        self._yandex_token.setPlaceholderText("y0_AgAAAA…")
        self._yandex_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._yandex_token.returnPressed.connect(self._on_save_yandex_token)
        self._reveal = QAction("Показать", self._yandex_token)
        self._reveal.setToolTip("Показать или скрыть токен")
        self._reveal.triggered.connect(self._toggle_token_visible)
        self._yandex_token.addAction(
            self._reveal, QLineEdit.ActionPosition.TrailingPosition
        )
        row.addWidget(self._yandex_token, stretch=1)
        self._save_token_btn = _button(
            "Сохранить", "searchButton", self._on_save_yandex_token
        )
        row.addWidget(self._save_token_btn)
        self._cancel_token_btn = _button(
            "Отмена", "settingsButton", self._cancel_yandex_edit
        )
        row.addWidget(self._cancel_token_btn)
        self._drop_token_btn = _button(
            "Отключить", "memberDanger", self._on_delete_yandex_token
        )
        row.addWidget(self._drop_token_btn)
        editor.addLayout(row)
        body.addWidget(self._yandex_editor)

        self._token_feedback = _label("", "memberFeedback", wrap=True)
        self._token_feedback.setTextFormat(Qt.TextFormat.RichText)
        self._token_feedback.setOpenExternalLinks(True)
        self._token_feedback.setVisible(False)
        body.addWidget(self._token_feedback)

        self._yandex_guide = _Guide("Как получить токен", _YANDEX_GUIDE)
        body.addWidget(self._yandex_guide)

    def _toggle_token_visible(self) -> None:
        hidden = self._yandex_token.echoMode() == QLineEdit.EchoMode.Password
        self._yandex_token.setEchoMode(
            QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password
        )
        self._reveal.setText("Скрыть" if hidden else "Показать")

    def _edit_yandex_token(self) -> None:
        self._yandex_editing = True
        self._sync_access()
        self._yandex_token.setFocus()

    def _cancel_yandex_edit(self) -> None:
        self._yandex_editing = False
        self._yandex_token.clear()
        self._hide_feedback(self._token_feedback)
        self._sync_access()

    def _on_save_yandex_token(self) -> None:
        text = self._yandex_token.text().strip()
        if not text:
            self._feedback(self._token_feedback, "error", "Вставь токен в поле.")
            return
        try:
            save_yandex_token(text)
        except ValueError as exc:
            self._feedback(self._token_feedback, "error", str(exc))
            return
        except Exception:
            logger.exception("Не удалось сохранить токен Яндекса")
            self._feedback(
                self._token_feedback,
                "error",
                "Не удалось сохранить токен в хранилище паролей системы.",
            )
            return
        self._yandex_token.clear()
        self._yandex_editing = False
        self._feedback(self._token_feedback, "", "Сохранено — проверяем аккаунт…")
        self._sync_access()
        self.refresh_membership()

    def _on_delete_yandex_token(self) -> None:
        try:
            delete_yandex_token()
        except Exception:
            logger.exception("Не удалось удалить токен Яндекса")
            self._feedback(self._token_feedback, "error", "Не удалось удалить токен.")
            return
        self._yandex_editing = False
        self._feedback(
            self._token_feedback,
            "warn",
            "Токен удалён с этого компьютера. Сам Яндекс его не отзывает — "
            "это можно сделать в "
            "<a href='https://id.yandex.ru/security/devices'>id.yandex.ru</a>.",
        )
        self._sync_access()
        self.refresh_membership()

    # --- YouTube ------------------------------------------------------------

    def _build_youtube_access(self, body: QVBoxLayout) -> None:
        self._youtube_saved = QWidget()
        saved = QHBoxLayout(self._youtube_saved)
        saved.setContentsMargins(0, 0, 0, 0)
        saved.setSpacing(8)
        saved.addWidget(
            _label("Куки сохранены на этом компьютере", "memberFeedback"), stretch=1
        )
        saved.addWidget(
            _button("Обновить куки", "settingsButton", self._edit_youtube_cookie)
        )
        saved.addWidget(
            _button("Отключить", "memberDanger", self._on_delete_youtube_cookie)
        )
        body.addWidget(self._youtube_saved)

        self._youtube_editor = QWidget()
        editor = QVBoxLayout(self._youtube_editor)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(6)
        editor.addWidget(_label("Куки или заголовки запроса", "memberFieldLabel"))
        self._youtube_cookie = QPlainTextEdit()
        self._youtube_cookie.setObjectName("memberCookieEdit")
        self._youtube_cookie.setPlaceholderText(
            "Заголовки запроса youtubei, JSON из Cookie-Editor или cookies.txt"
        )
        self._youtube_cookie.setFixedHeight(96)
        self._youtube_cookie.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        editor.addWidget(self._youtube_cookie)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._drop_cookie_btn = _button(
            "Отключить", "memberDanger", self._on_delete_youtube_cookie
        )
        actions.addWidget(self._drop_cookie_btn)
        actions.addStretch()
        self._cancel_cookie_btn = _button(
            "Отмена", "settingsButton", self._cancel_youtube_edit
        )
        actions.addWidget(self._cancel_cookie_btn)
        self._save_cookie_btn = _button(
            "Сохранить куки", "searchButton", self._on_save_youtube_cookie
        )
        actions.addWidget(self._save_cookie_btn)
        editor.addLayout(actions)
        body.addWidget(self._youtube_editor)

        self._cookie_feedback = _label("", "memberFeedback", wrap=True)
        self._cookie_feedback.setVisible(False)
        body.addWidget(self._cookie_feedback)

        self._youtube_guide = _Guide("Как скопировать куки", _YOUTUBE_GUIDE)
        body.addWidget(self._youtube_guide)

    def _edit_youtube_cookie(self) -> None:
        self._youtube_editing = True
        self._sync_access()
        self._youtube_cookie.setFocus()

    def _cancel_youtube_edit(self) -> None:
        self._youtube_editing = False
        self._youtube_cookie.clear()
        self._hide_feedback(self._cookie_feedback)
        self._sync_access()

    def _on_save_youtube_cookie(self) -> None:
        text = self._youtube_cookie.toPlainText().strip()
        if not text:
            self._feedback(
                self._cookie_feedback, "error", "Вставь куки или заголовки в поле."
            )
            return
        try:
            save_youtube_cookie(text)
        except ValueError as exc:
            # Тексты ValueError здесь уже человеческие: что не так и что вставить.
            self._feedback(self._cookie_feedback, "error", str(exc))
            return
        except Exception:
            logger.exception("Не удалось сохранить куки YouTube")
            self._feedback(
                self._cookie_feedback,
                "error",
                "Не удалось записать куки в файл. Попробуй ещё раз.",
            )
            return
        self._youtube_cookie.clear()
        self._youtube_editing = False
        self._feedback(self._cookie_feedback, "", "Сохранено — проверяем вход…")
        self._sync_access()
        self.refresh_membership()

    def _on_delete_youtube_cookie(self) -> None:
        try:
            delete_youtube_cookie()
        except Exception:
            logger.exception("Не удалось удалить куки YouTube")
            self._feedback(self._cookie_feedback, "error", "Не удалось удалить куки.")
            return
        self._youtube_editing = False
        self._feedback(
            self._cookie_feedback,
            "warn",
            "Куки удалены с этого компьютера. Слушать YouTube можно и без них.",
        )
        self._sync_access()
        self.refresh_membership()

    # --- общее --------------------------------------------------------------

    @staticmethod
    def _feedback(label: QLabel, state: str, text: str) -> None:
        label.setText(_with_links(text))
        _set_state(label, state)
        label.setVisible(True)

    @staticmethod
    def _hide_feedback(label: QLabel) -> None:
        label.clear()
        label.setVisible(False)

    def _sync_access(self) -> None:
        """Поле ввода — когда нечего показать или пользователь меняет данные;
        иначе одна строка «сохранено» с кнопками. Истёкшее — сразу поле."""
        snapshot = self._snapshot
        ya_saved = bool(yandex_token())
        ya_expired = (
            snapshot is not None and snapshot.yandex.state is AccountState.EXPIRED
        )
        ya_edit = self._yandex_editing or not ya_saved or ya_expired
        self._yandex_saved.setVisible(not ya_edit)
        self._yandex_editor.setVisible(ya_edit)
        self._cancel_token_btn.setVisible(self._yandex_editing)
        self._drop_token_btn.setVisible(ya_saved and not self._yandex_editing)

        yt_saved = bool(yotube_cookie())
        yt_expired = (
            snapshot is not None and snapshot.youtube.state is AccountState.EXPIRED
        )
        yt_edit = self._youtube_editing or not yt_saved or yt_expired
        self._youtube_saved.setVisible(not yt_edit)
        self._youtube_editor.setVisible(yt_edit)
        self._cancel_cookie_btn.setVisible(self._youtube_editing)
        # Куки истекли, но лежат на диске — их можно и просто убрать.
        self._drop_cookie_btn.setVisible(yt_saved and not self._youtube_editing)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._sync_access()
        self.refresh_membership()

    def refresh_membership(self) -> None:
        if self._bridge is None or self._loading:
            return
        self._loading = True
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("Проверяем…")
        self._yandex.show_checking()
        self._youtube.show_checking()
        self._bridge.schedule(self._load_membership())

    async def _load_membership(self) -> None:
        try:
            snapshot = await fetch_membership_snapshot()
        except Exception:
            logger.exception("Не удалось проверить аккаунты")
            snapshot = None
        if self._bridge is not None:
            self._bridge.invoke_main(lambda: self._apply_membership(snapshot))

    def _apply_membership(self, snapshot: MembershipSnapshot | None) -> None:
        self._loading = False
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("Проверить")
        if snapshot is None:
            failed = AccountStatus(
                AccountState.ERROR,
                "Не удалось проверить",
                "Что-то пошло не так. Нажми «Проверить», чтобы попробовать снова.",
            )
            snapshot = MembershipSnapshot(yandex=failed, youtube=failed)
        self._snapshot = snapshot
        self._yandex.show_status(snapshot.yandex)
        self._youtube.show_status(snapshot.youtube)
        # «Проверяем…» после сохранения сменился статусом в чипе.
        for label in (self._token_feedback, self._cookie_feedback):
            if label.property("state") in ("", None):
                self._hide_feedback(label)
        self._sync_access()
