"""Клиент магазина плагинов на сайте Quantis.

Список плагинов и скачивание — по токену аккаунта (``account.auth_headers()``).
Скачанный zip проверяется по размеру и SHA-256 из списка; при любой ошибке
частичный файл удаляется.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlparse

import aiohttp

logger = logging.getLogger(__name__)

MAX_PLUGIN_BYTES = 32 * 1024 * 1024
LIST_TIMEOUT_S = 15
DOWNLOAD_TIMEOUT_S = 60
_CHUNK = 64 * 1024
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

StoreAction = Literal["install", "update", "installed"]


class StoreAccount(Protocol):
    server_url: str

    def auth_headers(self) -> dict[str, str]: ...

    def handle_unauthorized(self) -> None: ...


class StoreError(Exception):
    """Ошибка магазина; текст можно показать пользователю."""


class StoreAuthError(StoreError):
    """Нет входа или токен отклонён."""


@dataclass(frozen=True)
class StorePlugin:
    plugin_id: str
    title: str
    version: str
    description: str
    author: str
    cover_url: str
    download_url: str
    size: int
    sha256: str


# ------------------------------------------------------------ версии


def _version_key(version: str) -> tuple[tuple[int, ...], str] | None:
    """(числовые части, хвост) или None, если версия не начинается с числа."""
    match = re.match(r"^\s*v?(\d+(?:\.\d+)*)(.*)$", version or "")
    if match is None:
        return None
    numbers = [int(part) for part in match.group(1).split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()  # 1.0 == 1.0.0
    return tuple(numbers), match.group(2).strip()


def is_newer(remote: str, local: str) -> bool:
    """Версия в магазине новее установленной (1.10.0 > 1.9.0, не строкой)."""
    remote_key = _version_key(remote)
    local_key = _version_key(local)
    if remote_key is None:
        return False
    if local_key is None:
        return True  # пустая или битая локальная версия — предлагаем обновить
    if remote_key[0] != local_key[0]:
        return remote_key[0] > local_key[0]
    # Одинаковые числа: релиз (без хвоста) новее пре-релиза (1.0.0 > 1.0.0-beta).
    remote_tail, local_tail = remote_key[1], local_key[1]
    if remote_tail == local_tail:
        return False
    if not remote_tail:
        return True
    if not local_tail:
        return False
    return remote_tail > local_tail


def store_action(item: StorePlugin, installed_version: str | None) -> StoreAction:
    if installed_version is None:
        return "install"
    return "update" if is_newer(item.version, installed_version) else "installed"


# ------------------------------------------------------------ сеть


def _require_safe_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS:
        return  # локальный сайт разработчика
    raise StoreError("Магазин работает только по https")


def _origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlparse(url)
    port = parsed.port or {"https": 443, "http": 80}.get(parsed.scheme)
    return parsed.scheme, (parsed.hostname or "").lower(), port


def _check_auth(account: StoreAccount) -> dict[str, str]:
    headers = account.auth_headers()
    if not headers:
        raise StoreAuthError("Войдите в аккаунт Quantis")
    return headers


def _parse_item(raw: object) -> StorePlugin | None:
    if not isinstance(raw, dict):
        return None
    plugin_id = str(raw.get("id") or "")
    download_url = str(raw.get("download_url") or "")
    if not plugin_id or not download_url:
        return None
    try:
        size = int(raw.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    return StorePlugin(
        plugin_id=plugin_id,
        title=str(raw.get("title") or plugin_id),
        version=str(raw.get("version") or ""),
        description=str(raw.get("description") or ""),
        author=str(raw.get("author") or ""),
        cover_url=str(raw.get("cover_url") or ""),
        download_url=download_url,
        size=size,
        sha256=str(raw.get("sha256") or "").lower(),
    )


async def fetch_store(account: StoreAccount) -> list[StorePlugin]:
    headers = _check_auth(account)
    url = f"{account.server_url}/api/plugins/"
    _require_safe_url(url)
    try:
        timeout = aiohttp.ClientTimeout(total=LIST_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 401:
                    account.handle_unauthorized()
                    raise StoreAuthError("Войдите в аккаунт Quantis")
                if response.status != 200:
                    raise StoreError(f"Магазин ответил ошибкой {response.status}")
                data = await response.json(content_type=None)
    except StoreError:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise StoreError(f"Сервер недоступен: {account.server_url}") from exc
    except ValueError as exc:
        raise StoreError("Магазин прислал непонятный ответ") from exc
    if not isinstance(data, list):
        raise StoreError("Магазин прислал непонятный ответ")
    return [item for item in map(_parse_item, data) if item is not None]


async def download_plugin(
    account: StoreAccount, item: StorePlugin, dest_dir: Path
) -> Path:
    """Скачивает zip плагина в dest_dir и проверяет размер и SHA-256.

    Качаем в память (не больше 32 МБ) и пишем на диск только проверенный
    файл — оборванной или подменённой загрузки на диске не остаётся.
    """
    if item.size > MAX_PLUGIN_BYTES:
        raise StoreError(f"Плагин «{item.title}» слишком большой")
    _require_safe_url(item.download_url)
    if _origin(item.download_url) != _origin(account.server_url):
        # Токен аккаунта — только серверу аккаунта, не по ссылке из ответа.
        raise StoreError("Магазин дал ссылку на чужой адрес — скачивание отменено")
    headers = _check_auth(account)
    data = bytearray()
    try:
        timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT_S)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(item.download_url, headers=headers) as response:
                if response.status == 401:
                    account.handle_unauthorized()
                    raise StoreAuthError("Войдите в аккаунт Quantis")
                if response.status != 200:
                    raise StoreError(f"Скачивание не удалось: ошибка {response.status}")
                async for chunk in response.content.iter_chunked(_CHUNK):
                    data.extend(chunk)
                    if len(data) > MAX_PLUGIN_BYTES:
                        raise StoreError(f"Плагин «{item.title}» слишком большой")
    except StoreError:
        raise
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise StoreError(f"Скачивание не удалось: {exc}") from exc
    if item.size and len(data) != item.size:
        raise StoreError("Скачивание оборвалось — попробуйте ещё раз")
    if hashlib.sha256(data).hexdigest() != item.sha256:
        raise StoreError("Файл повреждён: контрольная сумма не совпала")
    try:
        path = await asyncio.to_thread(
            _write_zip, dest_dir, item.plugin_id, bytes(data)
        )
    except OSError as exc:
        raise StoreError(f"Не удалось сохранить плагин: {exc}") from exc
    logger.info(
        "Магазин: скачан %s v%s (%d байт)", item.plugin_id, item.version, len(data)
    )
    return path


def _write_zip(dest_dir: Path, plugin_id: str, data: bytes) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f"{plugin_id}-", suffix=".zip", dir=dest_dir)
    path = Path(name)
    try:
        with open(fd, "wb") as out:
            out.write(data)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path
