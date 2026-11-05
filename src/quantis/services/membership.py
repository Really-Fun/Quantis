"""Сводка по аккаунтам внешних сервисов: подключены ли и что это даёт.

Интерфейсу отдаём только состояние и человеческий текст. Технические
подробности (исключения, ответы API) остаются в логе — пользователю они не
помогают, а простыня JSON на странице пугает.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from quantis.config.clients import Clients
from quantis.config.credentials import yandex_token, yotube_cookie

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="membership")


class AccountState(str, Enum):
    OK = "ok"
    """Подключено, всё работает."""
    LIMITED = "limited"
    """Подключено, но без подписки — часть возможностей недоступна."""
    OFF = "off"
    """Ничего не сохранено."""
    EXPIRED = "expired"
    """Сохранено, но сервис больше не принимает: нужно обновить."""
    ERROR = "error"
    """Проверить не удалось (сеть, сбой сервиса) — сохранённое не трогаем."""


@dataclass(frozen=True, slots=True)
class AccountStatus:
    state: AccountState
    headline: str
    """Короткий статус для чипа: «Плюс до 12.11.2026», «Сессия истекла»."""
    detail: str = ""
    """Что это значит и что делать — одной-двумя фразами."""
    account: str | None = None
    """Имя аккаунта, если сервис его отдал."""
    until: str | None = None

    @property
    def connected(self) -> bool:
        return self.state in (AccountState.OK, AccountState.LIMITED)


@dataclass(frozen=True, slots=True)
class MembershipSnapshot:
    yandex: AccountStatus
    youtube: AccountStatus


def _format_date(raw: str | None) -> str | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y")
    except ValueError:
        return text[:10] if len(text) >= 10 else text


def _plus_until_from_status(status) -> str | None:
    sub = getattr(status, "subscription", None)
    if sub is None:
        return None
    end = _format_date(getattr(sub, "end", None))
    if end:
        return end
    non_auto = getattr(sub, "non_auto_renewable", None)
    if non_auto is not None:
        end = _format_date(getattr(non_auto, "end", None))
        if end:
            return end
    for bucket_name in ("auto_renewable", "family_auto_renewable"):
        items = getattr(sub, bucket_name, None) or []
        for item in items:
            if getattr(item, "finished", False):
                continue
            end = _format_date(getattr(item, "expires", None))
            if end:
                return end
    return None


def _is_network_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    text = str(exc).lower()
    return (
        name in ("NetworkError", "TimedOutError", "ConnectionError", "Timeout")
        or isinstance(exc, (ConnectionError, TimeoutError))
        or "timed out" in text
        or "connection" in text
        or "name resolution" in text
    )


_YANDEX_OFF = AccountStatus(
    AccountState.OFF,
    "Не подключено",
    "Без токена нет поиска по Яндекс Музыке и «Моей волны».",
)


async def _fetch_yandex() -> AccountStatus:
    if not yandex_token():
        return _YANDEX_OFF
    client = Clients().get_yandex_client()
    if client is None:
        return AccountStatus(
            AccountState.ERROR,
            "Нет связи",
            "Не удалось подключиться к Яндексу. Проверь интернет и нажми "
            "«Проверить».",
        )
    try:
        status = await client.account_status()
    except Exception as exc:
        logger.warning("Статус аккаунта Яндекса не получен", exc_info=True)
        if type(exc).__name__ == "UnauthorizedError":
            return AccountStatus(
                AccountState.EXPIRED,
                "Токен не действует",
                "Яндекс больше не принимает этот токен. Получи новый и вставь "
                "его ниже.",
            )
        if _is_network_error(exc):
            return AccountStatus(
                AccountState.ERROR,
                "Нет связи",
                "Яндекс не ответил. Проверь интернет и нажми «Проверить».",
            )
        return AccountStatus(
            AccountState.ERROR,
            "Не удалось проверить",
            "Яндекс ответил ошибкой. Токен сохранён — попробуй проверить позже.",
        )

    account = getattr(status, "account", None)
    name = None
    if account is not None:
        name = (
            getattr(account, "display_name", None)
            or getattr(account, "full_name", None)
            or getattr(account, "login", None)
        )
    plus = getattr(status, "plus", None)
    has_plus = bool(getattr(plus, "has_plus", False)) if plus is not None else False
    if not has_plus:
        return AccountStatus(
            AccountState.LIMITED,
            "Без Плюса",
            "Поиск и волна работают, но треки играют только 30-секундными "
            "отрывками.",
            account=name,
        )
    until = _plus_until_from_status(status)
    return AccountStatus(
        AccountState.OK,
        f"Плюс до {until}" if until else "Плюс активен",
        "Полные треки, «Моя волна» и поиск по каталогу.",
        account=name,
        until=until,
    )


def _find_key(node: Any, key: str) -> Any:
    """Первое значение ключа где угодно во вложенных dict/list."""
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _find_key(value, key)
            if found is not None:
                return found
    return None


def _runs_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    runs = value.get("runs") or []
    text = "".join(str(run.get("text") or "") for run in runs if isinstance(run, dict))
    return text.strip() or None


def youtube_account_from_menu(response: dict) -> tuple[bool, str | None]:
    """(вошли ли, имя) из ответа account/account_menu.

    ytmusicapi.get_account_info ищет шапку по жёсткому пути и падает KeyError
    с дампом всего ответа — и когда YouTube поменял разметку, и когда сессия
    просто истекла. Здесь ищем шапку аккаунта где угодно: нет её — не вошли.
    """
    header = _find_key(response, "activeAccountHeaderRenderer")
    if not isinstance(header, dict):
        return False, None
    name = _runs_text(header.get("accountName"))
    handle = _runs_text(header.get("channelHandle"))
    return True, name or handle


_YOUTUBE_OFF = AccountStatus(
    AccountState.OFF,
    "Не подключено",
    "Слушать можно и так. Вход нужен для библиотеки и рекомендаций YouTube " "Music.",
)


def _fetch_youtube_sync() -> AccountStatus:
    if not yotube_cookie():
        return _YOUTUBE_OFF
    try:
        yt = Clients().get_youtube_client()
        response = yt._send_request("account/account_menu", {})
    except Exception as exc:
        logger.warning("Меню аккаунта YouTube Music не получено", exc_info=True)
        if _is_network_error(exc):
            return AccountStatus(
                AccountState.ERROR,
                "Нет связи",
                "YouTube не ответил. Проверь интернет и нажми «Проверить».",
            )
        return AccountStatus(
            AccountState.ERROR,
            "Не удалось проверить",
            "YouTube ответил ошибкой. Куки сохранены — попробуй проверить позже.",
        )
    logged_in, name = youtube_account_from_menu(response or {})
    if not logged_in:
        return AccountStatus(
            AccountState.EXPIRED,
            "Сессия истекла",
            "YouTube больше не узнаёт эти куки. Войди в music.youtube.com в "
            "браузере, скопируй их заново и вставь ниже.",
        )
    return AccountStatus(
        AccountState.OK,
        "Вход выполнен",
        "Библиотека и рекомендации YouTube Music. Premium API не показывает.",
        account=name,
    )


async def fetch_membership_snapshot() -> MembershipSnapshot:
    loop = asyncio.get_running_loop()
    youtube_job = loop.run_in_executor(_executor, _fetch_youtube_sync)
    yandex = await _fetch_yandex()
    youtube = await youtube_job
    return MembershipSnapshot(yandex=yandex, youtube=youtube)
