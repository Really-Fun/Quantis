"""Источники треков беты: YouTube (yt-dlp) и Яндекс Музыка (yandex-music).

Все функции блокирующие: их вызывают из пула потоков, а не из интерфейса.
resolve() отдаёт адрес для QMediaPlayer: локальный файл (YouTube качается
целиком — ссылкам googlevideo нужны заголовки, которых QMediaPlayer не
передаёт) или прямую ссылку Яндекса, которая играет потоком сразу.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
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
_fetch_locks: dict[str, threading.Lock] = {}
_fetch_locks_guard = threading.Lock()


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
            )
        )
    return results


def _youtube_attempts(outtmpl: str) -> list[tuple[str, dict]]:
    common = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
        "outtmpl": outtmpl,
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


def fetch_youtube(video_id: str, cache: Path) -> Path:
    """Скачанный звук; уже скачанный (или качающийся сейчас) — не качается снова."""
    global _android_client_ok
    import yt_dlp

    with _fetch_locks_guard:
        lock = _fetch_locks.setdefault(video_id, threading.Lock())
    with lock:  # трек и его предзагрузка не качают один файл вдвоём
        for existing in cache.glob(f"{video_id}.*"):
            if existing.suffix not in (".part", ".ytdl"):
                return existing
        url = f"https://www.youtube.com/watch?v={video_id}"
        error: Exception | None = None
        for name, opts in _youtube_attempts(str(cache / "%(id)s.%(ext)s")):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    path = Path(ydl.prepare_filename(info))
                if path.exists():
                    return path
            except Exception as exc:
                error = exc
                if name == "android" and "format is not available" in str(exc):
                    _android_client_ok = False
        if error is not None and "not a bot" in str(error):
            raise RuntimeError(
                "YouTube просит подтвердить, что вы не бот. Попробуйте позже "
                "или найдите трек в Яндексе."
            )
        raise RuntimeError(f"Не удалось скачать трек: {error}")


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
        if track.available is False or not track.id:
            continue
        title = track.title or str(track.id)
        if track.version:
            title = f"{title} ({track.version})"
        artist = ", ".join(a.name for a in (track.artists or []) if a.name)
        results.append(
            Result(
                source=YANDEX,
                track_id=str(track.id),
                title=title,
                artist=artist,
                duration=int(track.duration_ms or 0) // 1000,
            )
        )
        if len(results) >= SEARCH_LIMIT:
            break
    return results


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


def resolve(result: Result, token: str, cache: Path) -> str:
    """Адрес для QMediaPlayer: file:// для YouTube, https:// для Яндекса."""
    if result.source == YANDEX:
        return resolve_yandex(token, result.track_id)
    return fetch_youtube(result.track_id, cache).as_uri()
