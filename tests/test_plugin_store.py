"""Клиент магазина плагинов: список, скачивание с проверкой, сравнение версий."""

from __future__ import annotations

import hashlib
import socket

import pytest
import pytest_asyncio
from aiohttp import web

from quantis.plugins.store import (
    StoreAuthError,
    StoreError,
    StorePlugin,
    download_plugin,
    fetch_store,
    is_newer,
    store_action,
)

ZIP = b"PK\x03\x04" + b"x" * 200


class _Account:
    def __init__(self, server_url: str, token: str = "tok") -> None:
        self.server_url = server_url
        self.token = token
        self.unauthorized = 0

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self.token}"} if self.token else {}

    def handle_unauthorized(self) -> None:
        self.unauthorized += 1


async def _serve(state: dict) -> tuple[web.AppRunner, str]:
    def authorized(request: web.Request) -> bool:
        return request.headers.get("Authorization") == "Token tok"

    async def listing(request: web.Request) -> web.Response:
        if not authorized(request):
            return web.json_response({"detail": "auth"}, status=401)
        base = str(request.url.origin())
        return web.json_response(
            [
                {
                    "id": "together",
                    "title": "Together",
                    "version": "0.6.0",
                    "description": "Вместе",
                    "author": "Really-Fun",
                    "cover_url": "",
                    "download_url": f"{base}/api/plugins/together/download/",
                    "size": len(ZIP),
                    "sha256": hashlib.sha256(ZIP).hexdigest(),
                    "updated_at": "2026-11-09T00:00:00+00:00",
                }
            ]
        )

    async def download(request: web.Request) -> web.Response:
        if not authorized(request):
            return web.json_response({"detail": "auth"}, status=401)
        return web.Response(body=state.get("body", ZIP))

    app = web.Application()
    app.router.add_get("/api/plugins/", listing)
    app.router.add_get("/api/plugins/{plugin_id}/download/", download)
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


def _item(url: str, **extra) -> StorePlugin:
    fields = {
        "plugin_id": "together",
        "title": "Together",
        "version": "0.6.0",
        "description": "",
        "author": "",
        "cover_url": "",
        "download_url": f"{url}/api/plugins/together/download/",
        "size": len(ZIP),
        "sha256": hashlib.sha256(ZIP).hexdigest(),
    }
    fields.update(extra)
    return StorePlugin(**fields)


@pytest.mark.parametrize(
    ("remote", "local", "expected"),
    [
        ("1.10.0", "1.9.0", True),
        ("1.0", "1.0.0", False),
        ("0.5.1", "0.5.0", True),
        ("1.0.0", "", True),
        ("1.0.0", "2.0", False),
        ("1.0.0", "1.0.0-beta", True),
        ("1.0.0", "garbage", True),
    ],
)
def test_is_newer(remote: str, local: str, expected: bool) -> None:
    assert is_newer(remote, local) is expected


def test_store_action() -> None:
    item = _item("https://x")
    assert store_action(item, None) == "install"
    assert store_action(item, "0.5.0") == "update"
    assert store_action(item, "0.6.0") == "installed"
    assert store_action(item, "0.7.0") == "installed"


@pytest.mark.asyncio
async def test_fetch_store_parses_items(server) -> None:
    url, _ = server
    items = await fetch_store(_Account(url))
    assert items == [_item(url, description="Вместе", author="Really-Fun")]


@pytest.mark.asyncio
async def test_fetch_store_401_raises_auth_error(server) -> None:
    url, _ = server
    account = _Account(url, token="revoked")
    with pytest.raises(StoreAuthError):
        await fetch_store(account)
    assert account.unauthorized == 1


@pytest.mark.asyncio
async def test_fetch_store_requires_login() -> None:
    with pytest.raises(StoreAuthError):
        await fetch_store(_Account("https://x", token=""))


@pytest.mark.asyncio
async def test_fetch_store_network_error() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    with pytest.raises(StoreError, match="Сервер недоступен"):
        await fetch_store(_Account(f"http://127.0.0.1:{port}"))


@pytest.mark.asyncio
async def test_download_ok(server, tmp_path) -> None:
    url, _ = server
    path = await download_plugin(_Account(url), _item(url), tmp_path)
    assert path.read_bytes() == ZIP
    assert path.parent == tmp_path


@pytest.mark.asyncio
async def test_download_rejects_sha_mismatch(server, tmp_path) -> None:
    url, state = server
    state["body"] = b"PK\x03\x04" + b"y" * 200  # тот же размер, другое содержимое
    with pytest.raises(StoreError, match="контрольная сумма"):
        await download_plugin(_Account(url), _item(url), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_download_rejects_truncated(server, tmp_path) -> None:
    url, state = server
    state["body"] = ZIP[:50]
    with pytest.raises(StoreError):
        await download_plugin(_Account(url), _item(url), tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_download_rejects_too_big_item(server, tmp_path) -> None:
    url, _ = server
    with pytest.raises(StoreError, match="слишком большой"):
        await download_plugin(
            _Account(url), _item(url, size=64 * 1024 * 1024), tmp_path
        )


@pytest.mark.asyncio
async def test_download_rejects_plain_http_to_remote_host(tmp_path) -> None:
    item = _item("http://example.org")
    with pytest.raises(StoreError, match="https"):
        await download_plugin(_Account("http://example.org"), item, tmp_path)
