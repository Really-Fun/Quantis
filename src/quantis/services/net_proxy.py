"""Прокси для YouTube: один адрес на всё, что ходит к YouTube.

Там, где YouTube замедлен или закрыт, напрямую не работает ни поиск ссылки
(yt-dlp, ytmusicapi), ни сам поток (googlevideo). Ссылка на поток привязана к
IP, с которого её получили, поэтому через прокси должно идти всё сразу:
извлечение, звук, клип для фона, обложки и скачивание. Яндекс и SoundCloud
прокси не трогает.

Адрес задаёт интерфейс (``UiPreferences.youtube_proxy``); сервисы читают его
отсюда и не зависят от Qt.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_SCHEMES = ("http", "socks5", "socks5h", "socks4")
_YOUTUBE_HOSTS = (
    "youtube.com",
    "youtu.be",
    "googlevideo.com",
    "ytimg.com",
    "ggpht.com",
    "youtube-nocookie.com",
)
CHECK_URL = "https://www.youtube.com/generate_204"
_CHECK_TIMEOUT_SEC = 8.0

_proxy = ""
_listeners: list[Callable[[], None]] = []


def normalize_proxy(text: str | None) -> str:
    """Адрес прокси в виде ``схема://[логин:пароль@]хост:порт``; пусто — без
    прокси. ``127.0.0.1:8080`` без схемы считается HTTP-прокси.

    ValueError — с понятным пользователю текстом."""
    raw = (text or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"http://{raw}"
    parts = urlsplit(raw)
    scheme = parts.scheme.lower()
    if scheme not in _SCHEMES:
        raise ValueError("Поддерживаются прокси http://, socks5:// и socks4://")
    if not parts.hostname:
        raise ValueError("Не указан адрес прокси, например socks5://127.0.0.1:1080")
    try:
        port = parts.port
    except ValueError:
        raise ValueError("Некорректный порт прокси") from None
    if port is None:
        raise ValueError("Не указан порт прокси, например socks5://127.0.0.1:1080")
    return f"{scheme}://{parts.netloc}"


def set_youtube_proxy(text: str | None) -> None:
    """Задаёт прокси (некорректный адрес — как пустой) и сообщает подписчикам:
    ссылки, полученные с другого IP, больше не годятся."""
    global _proxy
    try:
        value = normalize_proxy(text)
    except ValueError:
        logger.warning("Прокси YouTube задан с ошибкой и не используется")
        value = ""
    if value == _proxy:
        return
    _proxy = value
    logger.info("Прокси YouTube: %s", proxy_label() or "выключен")
    for listener in list(_listeners):
        try:
            listener()
        except Exception:
            logger.exception("Подписчик смены прокси упал")


def youtube_proxy() -> str:
    return _proxy


def on_proxy_changed(listener: Callable[[], None]) -> None:
    _listeners.append(listener)


def proxy_label() -> str:
    """Прокси для сообщений и логов: без логина и пароля."""
    if not _proxy:
        return ""
    parts = urlsplit(_proxy)
    return f"{parts.scheme}://{parts.hostname}:{parts.port}"


def _remote_dns(url: str) -> str:
    """socks5 → socks5h: имена разрешает прокси. Местный DNS для YouTube
    бывает подменён, а yt-dlp и requests с socks5 спрашивают именно его."""
    if url.startswith("socks5://"):
        return "socks5h://" + url[len("socks5://") :]
    return url


def ytdlp_proxy() -> str | None:
    return _remote_dns(_proxy) if _proxy else None


def with_youtube_proxy(opts: dict[str, Any]) -> dict[str, Any]:
    """Опции yt-dlp с прокси YouTube, если он задан."""
    proxy = ytdlp_proxy()
    return {**opts, "proxy": proxy} if proxy else opts


def requests_proxies() -> dict[str, str] | None:
    """Прокси в формате requests (ytmusicapi)."""
    proxy = ytdlp_proxy()
    return {"http": proxy, "https": proxy} if proxy else None


def aiohttp_connector() -> Any | None:
    """Коннектор aiohttp через прокси YouTube; None — прокси не задан."""
    if not _proxy:
        return None
    from aiohttp_socks import ProxyConnector

    url = _proxy
    if url.startswith("socks5h://"):
        url = "socks5://" + url[len("socks5h://") :]
    return ProxyConnector.from_url(url, rdns=True)


def is_youtube_url(url: str | None) -> bool:
    host = (urlsplit(url or "").hostname or "").lower()
    return any(host == name or host.endswith(f".{name}") for name in _YOUTUBE_HOSTS)


async def check_youtube() -> tuple[bool, str]:
    """Достучаться до YouTube текущим способом (через прокси или напрямую).

    Возвращает (получилось, текст для пользователя)."""
    import aiohttp

    via = f"через прокси {proxy_label()}" if _proxy else "напрямую"
    started = time.monotonic()
    try:
        async with aiohttp.ClientSession(
            connector=aiohttp_connector(),
            timeout=aiohttp.ClientTimeout(total=_CHECK_TIMEOUT_SEC),
        ) as session:
            async with session.get(CHECK_URL, allow_redirects=False) as response:
                status = response.status
    except Exception as exc:
        logger.info("Проверка YouTube %s не прошла: %r", via, exc)
        if _proxy:
            return False, (
                f"YouTube не отвечает {via}. Проверьте, что прокси запущен "
                "и адрес указан верно."
            )
        return False, (
            "YouTube не отвечает напрямую. Похоже, в вашей сети он закрыт — "
            "укажите прокси."
        )
    seconds = time.monotonic() - started
    if status >= 400:
        return False, f"YouTube ответил ошибкой {status} {via}."
    return True, f"YouTube доступен {via} ({seconds:.1f} с)."
