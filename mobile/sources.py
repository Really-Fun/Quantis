"""Источники треков беты: YouTube (yt-dlp) и Яндекс Музыка (yandex-music).

Все функции блокирующие: их вызывают из пула потоков, а не из интерфейса.
resolve() отдаёт адрес для QMediaPlayer: прямую ссылку Яндекса или адрес
локального прокси для YouTube (ссылкам googlevideo нужны заголовки, которых
QMediaPlayer не передаёт — их добавляет stream_proxy). Оба играют сразу.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

SEARCH_LIMIT = 20
YANDEX, YOUTUBE = "yandex", "youtube"

T = TypeVar("T")


@dataclass(frozen=True)
class Result:
    source: str
    track_id: str
    title: str
    artist: str
    duration: int  # секунды, 0 — неизвестно
    cover: str = ""  # https-адрес обложки, "" — нет

    @property
    def label(self) -> str:
        minutes, seconds = divmod(self.duration, 60)
        length = f"  ·  {minutes}:{seconds:02d}" if self.duration else ""
        return f"{self.title}\n{self.artist}{length}"


def warm_up() -> None:
    """Импорт тяжёлых библиотек заранее: на телефоне это секунды."""
    import yandex_music  # noqa: F401
    import yt_dlp  # noqa: F401


# --- YouTube ----------------------------------------------------------------

_AUDIO_FORMAT = (
    "ba[protocol=https][ext=m4a]/ba[protocol=https]/bestaudio[protocol=https]/bestaudio"
)
# Клиент android быстрее, но для многих видео отвечает «формат недоступен»:
# после первого такого отказа за сессию его больше не пробуем (−1,2 с на трек).
_android_client_ok = True
_stream_locks: dict[str, threading.Lock] = {}
_stream_locks_guard = threading.Lock()
_streams: dict[str, YoutubeStream] = {}


@dataclass(frozen=True)
class YoutubeStream:
    """Прямая ссылка googlevideo и заголовки, без которых она не отвечает."""

    url: str
    headers: dict[str, str]
    content_type: str
    size: int | None
    expires: float


def search_youtube(query: str) -> list[Result]:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{SEARCH_LIMIT}:{query}", download=False)
    results = []
    for entry in (info or {}).get("entries") or []:
        video_id = entry.get("id")
        if not video_id:
            continue
        results.append(
            Result(
                source=YOUTUBE,
                track_id=video_id,
                title=entry.get("title") or video_id,
                artist=entry.get("channel") or entry.get("uploader") or "",
                duration=int(entry.get("duration") or 0),
                # hqdefault есть у любого видео; квадрат вырезает art.py.
                cover=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            )
        )
    return results


def _youtube_attempts() -> list[tuple[str, dict]]:
    common = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": _AUDIO_FORMAT,
    }
    attempts = []
    if _android_client_ok:
        attempts.append(
            (
                "android",
                {
                    **common,
                    "extractor_args": {
                        "youtube": {
                            "player_client": ["android"],
                            "skip": ["hls", "dash", "translated_subs"],
                            "player_skip": ["webpage", "configs"],
                        }
                    },
                },
            )
        )
    attempts.append(("default", common))
    return attempts


def _expires(url: str) -> float:
    """Срок ссылки из её параметра expire, с запасом в 5 минут."""
    from urllib.parse import parse_qs, urlparse

    try:
        expire = float(parse_qs(urlparse(url).query)["expire"][0])
    except (KeyError, IndexError, ValueError):
        return time.time() + 1800
    return expire - 300


def youtube_stream(video_id: str, *, fresh: bool = False) -> YoutubeStream:
    """Ссылка на звук без скачивания; живая ссылка берётся из кэша.

    fresh=True — googlevideo ответил 403, ссылку нужно получить заново.
    """
    global _android_client_ok
    import yt_dlp

    with _stream_locks_guard:
        lock = _stream_locks.setdefault(video_id, threading.Lock())
    with lock:  # трек и его предзагрузка не разбирают одно видео вдвоём
        cached = _streams.get(video_id)
        if cached is not None and not fresh and cached.expires > time.time():
            return cached
        url = f"https://www.youtube.com/watch?v={video_id}"
        error: Exception | None = None
        for name, opts in _youtube_attempts():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as exc:
                error = exc
                if name == "android" and "format is not available" in str(exc):
                    _android_client_ok = False
                continue
            stream_url = info.get("url")
            if not stream_url:
                continue
            ext = info.get("ext") or "m4a"
            stream = YoutubeStream(
                url=stream_url,
                headers={
                    str(k): str(v) for k, v in (info.get("http_headers") or {}).items()
                },
                content_type="audio/webm" if ext == "webm" else "audio/mp4",
                size=info.get("filesize") or None,
                expires=_expires(stream_url),
            )
            _streams[video_id] = stream
            return stream
        if error is not None and "not a bot" in str(error):
            raise RuntimeError(
                "YouTube просит подтвердить, что вы не бот. Попробуйте позже "
                "или найдите трек в Яндексе."
            )
        raise RuntimeError(f"YouTube не отдал звук: {error}")


# --- Яндекс Музыка ----------------------------------------------------------

# Как в настольном Quantis: download-info с одного токена Яндекс отдаёт по
# одному запросу за раз (429 «Concurrency limit»), поэтому запросы идут по
# очереди, а при отказе повторяются с паузой и разбросом.
_RATE_LIMIT_RETRIES = (0.5, 1.0, 2.0, 3.0)
_yandex_lock = threading.Lock()
_clients: dict[str, object] = {}


def _rate_limited(exc: BaseException) -> bool:
    text = str(exc)
    return "(429)" in text or "Concurrency limit" in text


def _yandex(call: Callable[[], T]) -> T:
    with _yandex_lock:
        for delay in (*_RATE_LIMIT_RETRIES, None):
            try:
                return call()
            except Exception as exc:
                if delay is None or not _rate_limited(exc):
                    raise
                time.sleep(delay * random.uniform(0.8, 1.3))
    raise AssertionError("недостижимо")


def _client(token: str):
    from yandex_music import Client

    client = _clients.get(token)
    if client is None:
        client = _clients[token] = Client(token)
    return client


def check_yandex_token(token: str) -> str:
    """Логин аккаунта; бросает исключение, если токен не подходит."""
    from yandex_music import Client

    client = _yandex(lambda: Client(token).init())
    account = client.me.account if client.me else None
    login = (account.login or account.display_name) if account else ""
    plus = bool(client.me and client.me.plus and client.me.plus.has_plus)
    return f"{login or 'аккаунт'}{' · Плюс' if plus else ' · без Плюса'}"


def search_yandex(token: str, query: str) -> list[Result]:
    client = _client(token)
    found = _yandex(lambda: client.search(query, type_="track"))
    tracks = found.tracks.results if found and found.tracks else []
    results = []
    for track in tracks:
        result = yandex_result(track)
        if result is not None:
            results.append(result)
        if len(results) >= SEARCH_LIMIT:
            break
    return results


def yandex_result(track) -> Result | None:
    """Трек yandex-music → Result; недоступный (нет прав, удалён) — None."""
    if track is None or track.available is False or not track.id:
        return None
    title = track.title or str(track.id)
    if track.version:
        title = f"{title} ({track.version})"
    artist = ", ".join(a.name for a in (track.artists or []) if a.name)
    return Result(
        source=YANDEX,
        track_id=str(track.id),
        title=title,
        artist=artist,
        duration=int(track.duration_ms or 0) // 1000,
        cover=_yandex_cover(track.cover_uri or track.og_image or ""),
    )


def _yandex_cover(uri: str, size: int = 400) -> str:
    """avatars.yandex.net/…/%% → https-адрес квадратной обложки size×size."""
    if not uri:
        return ""
    return "https://" + uri.replace("%%", f"{size}x{size}")


def _best_download_info(infos: list) -> object | None:
    """Полный трек, а не превью; mp3 предпочтительнее, затем битрейт."""

    def rank(item) -> tuple:
        codec = str(getattr(item, "codec", "") or "").lower()
        return (
            0 if getattr(item, "preview", False) else 1,
            2 if codec == "mp3" else (1 if codec in ("aac", "mp4") else 0),
            int(getattr(item, "bitrate_in_kbps", 0) or 0),
        )

    return max(infos, key=rank) if infos else None


def resolve_yandex(token: str, track_id: str) -> str:
    """Прямая ссылка на звук: QMediaPlayer играет её потоком, без скачивания."""
    client = _client(token)
    tracks = _yandex(lambda: client.tracks([track_id]))
    if not tracks:
        raise RuntimeError("Трек не найден в Яндекс Музыке")
    infos = _yandex(lambda: tracks[0].get_download_info()) or []
    chosen = _best_download_info(list(infos))
    if chosen is None:
        raise RuntimeError("Яндекс не отдал ссылку на трек")
    if getattr(chosen, "preview", False):
        raise RuntimeError("Полный трек доступен только с Плюсом — есть лишь превью")
    return _yandex(chosen.get_direct_link)


# --- общее ------------------------------------------------------------------


def resolve(result: Result, token: str, proxy) -> str:
    """Адрес для QMediaPlayer: https:// Яндекса или http://127.0.0.1 прокси."""
    if result.source == YANDEX:
        return resolve_yandex(token, result.track_id)
    youtube_stream(result.track_id)  # ошибка YouTube — сейчас, а не в плеере
    return proxy.url_for(result.track_id)
