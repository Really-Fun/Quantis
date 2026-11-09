"""Аккаунт сайта Quantis: вход по логину и паролю → токен API.

Один вход на всё, что ходит на сайт: магазин плагинов, Together. Пароль
нигде не хранится; токен — в keyring, имя и адрес сервера — в QSettings.
Если keyring недоступен, токен живёт в памяти до перезапуска.
"""

from __future__ import annotations

import logging

import aiohttp
from keyring.errors import KeyringError
from PySide6.QtCore import QObject, QSettings, Signal

from quantis.config import credentials

logger = logging.getLogger(__name__)

DEFAULT_SERVER = "https://212-87-190-34.nip.io"
REQUEST_TIMEOUT_S = 15

_KEY_USERNAME = "account/username"
_KEY_SERVER = "account/server"


class AccountError(Exception):
    """Ошибка входа; текст можно показать пользователю как есть."""


class QuantisAccount(QObject):
    changed = Signal()

    def __init__(self, settings: QSettings | None = None) -> None:
        super().__init__()
        self._settings = settings or QSettings("ReallyFun", "Quantis")
        self._token = credentials.load_quantis_token()
        self._token_persisted = True
        self._username = str(self._settings.value(_KEY_USERNAME, "") or "")

    # ------------------------------------------------------------ состояние

    @property
    def server_url(self) -> str:
        value = str(self._settings.value(_KEY_SERVER, "") or "").strip()
        return value.rstrip("/") or DEFAULT_SERVER

    def set_server_url(self, url: str) -> None:
        self._settings.setValue(_KEY_SERVER, url.strip().rstrip("/"))

    @property
    def username(self) -> str:
        return self._username

    @property
    def token(self) -> str:
        return self._token

    @property
    def is_logged_in(self) -> bool:
        return bool(self._token)

    @property
    def token_persisted(self) -> bool:
        """False — keyring недоступен, токен пропадёт после перезапуска."""
        return self._token_persisted

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {self._token}"} if self._token else {}

    # ------------------------------------------------------------ сеть

    def _url(self, path: str) -> str:
        return f"{self.server_url}{path}"

    @staticmethod
    def _timeout() -> aiohttp.ClientTimeout:
        return aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S)

    async def login(self, username: str, password: str) -> None:
        username = username.strip()
        if not username or not password:
            raise AccountError("Введите логин и пароль")
        try:
            async with aiohttp.ClientSession(timeout=self._timeout()) as session:
                async with session.post(
                    self._url("/api/auth/token/"),
                    json={"username": username, "password": password},
                ) as response:
                    data = await _json(response)
                    status = response.status
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise AccountError(f"Сервер недоступен: {self.server_url}") from exc
        if status == 429:
            raise AccountError("Слишком много попыток входа — подождите минуту")
        token = str(data.get("token") or "") if status == 200 else ""
        if not token:
            raise AccountError(str(data.get("detail") or "Не удалось войти"))
        self._username = str(data.get("username") or username)
        self._settings.setValue(_KEY_USERNAME, self._username)
        self._set_token(token)
        logger.info("Аккаунт Quantis: вошли как %s", self._username)
        self.changed.emit()

    async def logout(self) -> None:
        """Забывает токен; сервер просим его удалить, но не ждём успеха."""
        if self._token:
            try:
                async with aiohttp.ClientSession(timeout=self._timeout()) as session:
                    async with session.delete(
                        self._url("/api/auth/token/"), headers=self.auth_headers()
                    ):
                        pass
            except (aiohttp.ClientError, TimeoutError):
                logger.info("Аккаунт Quantis: сервер недоступен, токен забыт локально")
        self._forget()

    async def verify(self) -> bool:
        """Проверяет токен. 401 — разлогин; нет сети — токен остаётся."""
        if not self._token:
            return False
        try:
            async with aiohttp.ClientSession(timeout=self._timeout()) as session:
                async with session.get(
                    self._url("/api/auth/me/"), headers=self.auth_headers()
                ) as response:
                    if response.status == 401:
                        self.handle_unauthorized()
                        return False
                    if response.status == 200:
                        data = await _json(response)
                        name = str(data.get("username") or "")
                        if name and name != self._username:
                            self._username = name
                            self._settings.setValue(_KEY_USERNAME, name)
                            self.changed.emit()
        except (aiohttp.ClientError, TimeoutError):
            logger.info("Аккаунт Quantis: сервер недоступен, проверку токена пропускаем")
        return True

    def handle_unauthorized(self) -> None:
        """Сервер ответил 401: токен отозван — считаем, что вышли."""
        if self._token:
            logger.info("Аккаунт Quantis: токен отклонён сервером")
            self._forget()

    # ------------------------------------------------------------ внутреннее

    def _set_token(self, token: str) -> None:
        self._token = token
        try:
            credentials.save_quantis_token(token)
            self._token_persisted = True
        except KeyringError:
            logger.warning("keyring недоступен — токен Quantis только в памяти")
            self._token_persisted = False

    def _forget(self) -> None:
        self._token = ""
        self._token_persisted = True
        credentials.delete_quantis_token()
        self.changed.emit()


async def _json(response: aiohttp.ClientResponse) -> dict:
    try:
        data = await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}
