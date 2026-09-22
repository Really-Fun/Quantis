"""Сводка по подпискам / аккаунтам внешних сервисов."""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime

from quantis.config.clients import Clients
from quantis.config.credentials import yandex_token, yotube_cookie

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="membership")


@dataclass(frozen=True, slots=True)
class YandexMembershipInfo:
    connected: bool
    display_name: str | None = None
    has_plus: bool = False
    plus_until: str | None = None
    detail: str = ""
    error: str | None = None


@dataclass(frozen=True, slots=True)
class YoutubeMembershipInfo:
    connected: bool
    account_name: str | None = None
    channel_handle: str | None = None
    detail: str = ""
    error: str | None = None


@dataclass(frozen=True, slots=True)
class MembershipSnapshot:
    yandex: YandexMembershipInfo
    youtube: YoutubeMembershipInfo


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


async def _fetch_yandex() -> YandexMembershipInfo:
    if not yandex_token():
        return YandexMembershipInfo(
            connected=False,
            detail="Токен не задан — статус Plus недоступен",
        )
    client = Clients().get_yandex_client()
    if client is None:
        return YandexMembershipInfo(
            connected=False,
            detail="Клиент Yandex не инициализирован",
            error="Нет клиента",
        )
    try:
        status = await client.account_status()
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
        until = _plus_until_from_status(status) if has_plus else None
        if has_plus:
            detail = (
                f"Яндекс Плюс активен до {until}" if until else "Яндекс Плюс активен"
            )
        else:
            detail = "Яндекс Плюс на аккаунте не найден"
        return YandexMembershipInfo(
            connected=True,
            display_name=name,
            has_plus=has_plus,
            plus_until=until,
            detail=detail,
        )
    except Exception as exc:
        logger.exception("Не удалось получить статус Yandex")
        return YandexMembershipInfo(
            connected=True,
            detail="Не удалось загрузить статус аккаунта",
            error=str(exc),
        )


def _fetch_youtube_sync() -> YoutubeMembershipInfo:
    if not yotube_cookie():
        return YoutubeMembershipInfo(
            connected=False,
            detail=(
                "Cookies не заданы — библиотека и персональные "
                "рекомендации YouTube Music ограничены"
            ),
        )
    try:
        yt = Clients().get_youtube_client()
        info = yt.get_account_info()
        name = info.get("accountName")
        handle = info.get("channelHandle")
        who = name or handle or "аккаунт"
        return YoutubeMembershipInfo(
            connected=True,
            account_name=name,
            channel_handle=handle,
            detail=(
                f"Вход: {who}. Cookies дают доступ к библиотеке и "
                "персональной ленте; статус Premium API не отдаёт."
            ),
        )
    except Exception as exc:
        logger.exception("Не удалось получить аккаунт YouTube Music")
        return YoutubeMembershipInfo(
            connected=True,
            detail=(
                "Cookies сохранены, но проверить аккаунт не удалось. "
                "Premium через API недоступен."
            ),
            error=str(exc),
        )


async def fetch_membership_snapshot() -> MembershipSnapshot:
    yandex = await _fetch_yandex()
    loop = asyncio.get_running_loop()
    youtube = await loop.run_in_executor(_executor, _fetch_youtube_sync)
    return MembershipSnapshot(yandex=yandex, youtube=youtube)
