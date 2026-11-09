"""Аккаунт Quantis: вход по токену, хранение токена, выход, отзыв токена."""

from __future__ import annotations

import socket

import pytest
import pytest_asyncio
from aiohttp import web
from keyring.errors import KeyringError
from PySide6.QtCore import QSettings

from quantis.config import credentials
from quantis.services import quantis_account
from quantis.services.quantis_account import AccountError, QuantisAccount

GOOD_TOKEN = "tok-123"


class _Vault:
    """Подмена keyring: что сохранили — то и лежит."""

    def __init__(self) -> None:
        self.token = ""
        self.fail = False

    def save(self, token: str) -> None:
        if self.fail:
            raise KeyringError("no backend")
        self.token = token

    def load(self) -> str:
        return self.token

    def delete(self) -> None:
        self.token = ""


@pytest.fixture
def vault(monkeypatch) -> _Vault:
    box = _Vault()
    monkeypatch.setattr(credentials, "save_quantis_token", box.save)
    monkeypatch.setattr(credentials, "load_quantis_token", box.load)
    monkeypatch.setattr(credentials, "delete_quantis_token", box.delete)
    return box


@pytest.fixture
def settings(tmp_path) -> QSettings:
    return QSettings(str(tmp_path / "account.ini"), QSettings.Format.IniFormat)


async def _serve(state: dict) -> tuple[web.AppRunner, str]:
    async def token(request: web.Request) -> web.Response:
        if request.method == "DELETE":
            state["deleted"] = request.headers.get("Authorization")
            return web.Response(status=204)
        body = await request.json()
        if body == {"username": "u", "password": "secret"}:
            return web.json_response({"token": GOOD_TOKEN, "username": "u"})
        return web.json_response({"detail": "Неверный логин или пароль"}, status=400)

    async def me(request: web.Request) -> web.Response:
        if request.headers.get(
            "Authorization"
        ) == f"Token {GOOD_TOKEN}" and not state.get("revoked"):
            return web.json_response({"username": "u"})
        return web.json_response({"detail": "bad"}, status=401)

    app = web.Application()
    app.router.add_route("*", "/api/auth/token/", token)
    app.router.add_get("/api/auth/me/", me)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{runner.addresses[0][1]}"


@pytest_asyncio.fixture
async def server():
    state: dict = {}
    runner, url = await _serve(state)
    try:
        yield url, state
    finally:
        await runner.cleanup()


def _account(settings: QSettings, url: str) -> QuantisAccount:
    account = QuantisAccount(settings=settings)
    account.set_server_url(url)
    return account


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.mark.asyncio
async def test_login_saves_token_not_password(server, vault, settings) -> None:
    url, _ = server
    account = _account(settings, url)
    changes: list[bool] = []
    account.account_changed.connect(lambda: changes.append(account.is_logged_in))
    await account.login("u", "secret")
    assert account.is_logged_in
    assert account.username == "u"
    assert account.token == GOOD_TOKEN
    assert vault.token == GOOD_TOKEN
    assert account.token_persisted
    assert changes == [True]
    stored = {key: settings.value(key) for key in settings.allKeys()}
    assert "secret" not in str(stored)
    assert GOOD_TOKEN not in str(stored)


@pytest.mark.asyncio
async def test_login_wrong_password(server, vault, settings) -> None:
    url, _ = server
    account = _account(settings, url)
    with pytest.raises(AccountError, match="Неверный логин или пароль"):
        await account.login("u", "nope")
    assert not account.is_logged_in


@pytest.mark.asyncio
async def test_login_server_down(vault, settings) -> None:
    account = _account(settings, f"http://127.0.0.1:{_free_port()}")
    with pytest.raises(AccountError, match="Сервер недоступен"):
        await account.login("u", "secret")
    assert not account.is_logged_in


@pytest.mark.asyncio
async def test_logout_deletes_token_on_server(server, vault, settings) -> None:
    url, state = server
    account = _account(settings, url)
    await account.login("u", "secret")
    await account.logout()
    assert state["deleted"] == f"Token {GOOD_TOKEN}"
    assert not account.is_logged_in
    assert vault.token == ""


@pytest.mark.asyncio
async def test_logout_forgets_token_even_if_server_down(vault, settings) -> None:
    vault.token = GOOD_TOKEN
    settings.setValue("account/username", "u")
    account = _account(settings, f"http://127.0.0.1:{_free_port()}")
    assert account.is_logged_in
    await account.logout()
    assert not account.is_logged_in
    assert vault.token == ""


@pytest.mark.asyncio
async def test_verify_keeps_valid_token(server, vault, settings) -> None:
    url, _ = server
    vault.token = GOOD_TOKEN
    account = _account(settings, url)
    assert await account.verify()
    assert account.is_logged_in


@pytest.mark.asyncio
async def test_401_logs_out(server, vault, settings) -> None:
    url, state = server
    vault.token = GOOD_TOKEN
    settings.setValue("account/username", "u")
    account = _account(settings, url)
    changes: list[bool] = []
    account.account_changed.connect(lambda: changes.append(account.is_logged_in))
    state["revoked"] = True
    assert not await account.verify()
    assert not account.is_logged_in
    assert vault.token == ""
    assert changes == [False]


@pytest.mark.asyncio
async def test_verify_offline_keeps_token(vault, settings) -> None:
    """Сеть пропала — это не повод разлогинивать."""
    vault.token = GOOD_TOKEN
    account = _account(settings, f"http://127.0.0.1:{_free_port()}")
    assert await account.verify()
    assert account.is_logged_in


@pytest.mark.asyncio
async def test_login_without_keyring_keeps_token_in_memory(
    server, vault, settings
) -> None:
    url, _ = server
    vault.fail = True
    account = _account(settings, url)
    await account.login("u", "secret")
    assert account.is_logged_in
    assert not account.token_persisted


def test_auth_headers(vault, settings) -> None:
    account = QuantisAccount(settings=settings)
    assert account.auth_headers() == {}
    vault.token = "abc"
    account = QuantisAccount(settings=settings)
    assert account.auth_headers() == {"Authorization": "Token abc"}


def test_default_server(vault, settings) -> None:
    account = QuantisAccount(settings=settings)
    assert (
        account.server_url
        == quantis_account.DEFAULT_SERVER
        == "https://212-87-190-34.nip.io"
    )
    account.set_server_url("https://example.org/ ")
    assert account.server_url == "https://example.org"
    assert QuantisAccount(settings=settings).server_url == "https://example.org"


def test_plugin_host_exposes_account_and_opens_accounts(vault, settings) -> None:
    from quantis.core.plugin_host import PluginHost
    from quantis.plugins.event_bus import EventBus

    bus = EventBus()
    account = QuantisAccount(settings=settings)
    host = PluginHost(event_bus=bus, playback=None, music=None, account=account)
    opened: list[bool] = []
    bus.accounts_requested.connect(lambda: opened.append(True))
    host.open_accounts()
    assert host.account is account
    assert opened == [True]


@pytest.mark.asyncio
async def test_login_refuses_plain_http_to_remote_host(vault, settings) -> None:
    """Пароль не уходит открытым текстом на чужой сервер; локальный сайт — можно."""
    account = _account(settings, "http://example.org")
    with pytest.raises(AccountError, match="https"):
        await account.login("u", "secret")
