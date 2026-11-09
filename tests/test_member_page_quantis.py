"""Карточка аккаунта Quantis в «Аккаунтах»."""

from __future__ import annotations

import asyncio

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton

import quantis.models  # noqa: F401  — до providers (давний цикл импортов)
from quantis.services.quantis_account import AccountError
from quantis.ui.views import member_page
from quantis.ui.views.member_page import _QuantisCard


class _Account(QObject):
    account_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.username = ""
        self.token = ""
        self.token_persisted = True
        self.server_url = "https://212-87-190-34.nip.io"
        self.error: Exception | None = None
        self.logins: list[tuple[str, str]] = []

    @property
    def is_logged_in(self) -> bool:
        return bool(self.token)

    def set_server_url(self, url: str) -> None:
        self.server_url = url

    async def login(self, username: str, password: str) -> None:
        self.logins.append((username, password))
        if self.error is not None:
            raise self.error
        self.username, self.token = username, "tok"
        self.account_changed.emit()

    async def logout(self) -> None:
        self.token = ""
        self.account_changed.emit()


class _Bridge:
    """Корутины выполняем сразу, колбэки UI — тоже сразу."""

    def schedule(self, coro):
        asyncio.run(coro)

    def invoke_main(self, fn) -> None:
        fn()


@pytest.fixture
def card(qapp):
    account = _Account()
    widget = _QuantisCard(account, _Bridge())
    widget.resize(600, 400)
    widget.show()
    yield widget, account
    widget.close()


def _texts(widget) -> list[str]:
    return [w.text() for w in widget.findChildren(QLabel) if w.isVisible() and w.text()]


def _button(widget, text: str) -> QPushButton:
    return next(b for b in widget.findChildren(QPushButton) if b.text() == text)


def test_card_shows_login_form_when_logged_out(card) -> None:
    widget, _ = card
    assert widget._username.isVisible()
    assert widget._password.isVisible()
    assert widget._password.echoMode() == QLineEdit.EchoMode.Password
    assert _button(widget, "Войти").isVisible()
    assert not _button(widget, "Выйти").isVisible()


def test_login_switches_card(card) -> None:
    widget, account = card
    widget._username.setText("u")
    widget._password.setText("secret")
    _button(widget, "Войти").click()
    assert account.logins == [("u", "secret")]
    assert any("Вы вошли как u" in text for text in _texts(widget))
    assert _button(widget, "Выйти").isVisible()
    assert not widget._password.isVisible()


def test_password_field_cleared_after_login(card) -> None:
    widget, _ = card
    widget._username.setText("u")
    widget._password.setText("secret")
    _button(widget, "Войти").click()
    assert widget._password.text() == ""


def test_login_error_is_shown(card) -> None:
    widget, account = card
    account.error = AccountError("Неверный логин или пароль")
    widget._username.setText("u")
    widget._password.setText("nope")
    _button(widget, "Войти").click()
    assert "Неверный логин или пароль" in _texts(widget)
    assert _button(widget, "Войти").isEnabled()


def test_card_follows_account_changes(card) -> None:
    widget, account = card
    account.username, account.token = "u", "tok"
    account.account_changed.emit()
    assert _button(widget, "Выйти").isVisible()
    _button(widget, "Выйти").click()
    assert widget._username.isVisible()


def test_unsaved_token_is_explained(card) -> None:
    widget, account = card
    account.username, account.token, account.token_persisted = "u", "tok", False
    account.account_changed.emit()
    assert any("Токен не сохранён" in text for text in _texts(widget))


def test_server_field_is_hidden_until_advanced(card) -> None:
    widget, account = card
    assert not widget._server.isVisible()
    widget._advanced.click()
    assert widget._server.isVisible()
    widget._server.setText("http://127.0.0.1:8000")
    widget._server.editingFinished.emit()
    assert account.server_url == "http://127.0.0.1:8000"


def test_site_link_opens_server(card, monkeypatch) -> None:
    widget, account = card
    opened: list[str] = []
    monkeypatch.setattr(
        member_page.QDesktopServices, "openUrl", lambda url: opened.append(url.toString())
    )
    widget._site_link.linkActivated.emit("site")
    assert opened == [account.server_url]
