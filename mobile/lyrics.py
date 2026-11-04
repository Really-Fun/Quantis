"""Тексты песен: Яндекс (для его треков), иначе открытая база lrclib.net.

fetch() блокирующая — из пула потоков. Ответ — Lyrics: строки с временем
(LRC, синхронный текст) или без него. Найденное и «не нашлось» кладутся
в кэш на диске, чтобы второй раз — и без сети — не спрашивать.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path

import art
import sources
from PySide6.QtCore import QStandardPaths
from sources import YANDEX, Result

log = logging.getLogger(__name__)
_TIMEOUT = 15
_LRCLIB = "https://lrclib.net/api"
_LRC_LINE = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")
# Хвосты названий с YouTube, мешающие поиску: (Official Video), [Lyrics]…
_TITLE_NOISE = re.compile(
    r"\s*[\(\[][^)\]]*(official|video|audio|lyric|клип|mv|hd|4k|visualizer)[^)\]]*[\)\]]",
    re.I,
)


@dataclass
class Lyrics:
    lines: list[dict] = field(default_factory=list)  # {"t": мс или -1, "text": …}
    synced: bool = False
    source: str = ""  # «Яндекс Музыка», «LRCLIB» или "" — не нашлось


def parse_lrc(text: str) -> list[dict]:
    """[мм:сс.хх] строка → [{"t": мс, "text": строка}], по времени."""
    lines = []
    for raw in text.splitlines():
        stamps = list(_LRC_LINE.finditer(raw))
        if not stamps:
            continue
        words = raw[stamps[-1].end():].strip()
        for stamp in stamps:  # «[00:10][01:20] припев» — две строки
            seconds = float(stamp.group(2).replace(":", "."))
            lines.append({"t": int((int(stamp.group(1)) * 60 + seconds) * 1000), "text": words})
    return sorted(lines, key=lambda line: line["t"])


def _plain(text: str) -> list[dict]:
    return [{"t": -1, "text": line.strip()} for line in text.strip().splitlines()]


def _cache_path(result: Result) -> Path:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.CacheLocation)
    folder = Path(base or Path.home() / ".cache" / "quantis-mobile") / "lyrics"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{result.source}:{result.track_id}".encode()).hexdigest()
    return folder / f"{key}.json"


def cached(result: Result) -> Lyrics | None:
    try:
        return Lyrics(**json.loads(_cache_path(result).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def fetch(result: Result, token: str) -> Lyrics:
    """Текст трека: из кэша, иначе из сети (и в кэш)."""
    found = cached(result)
    if found is not None:
        return found
    found = None
    if result.source == YANDEX and token:
        try:
            found = _from_yandex(result, token)
        except Exception as exc:  # нет текста или прав — попробуем lrclib
            log.info("Текст из Яндекса не получен: %s", exc)
    if found is None:
        found = _from_lrclib(result)
    lyrics = found or Lyrics()
    _cache_path(result).write_text(json.dumps(asdict(lyrics), ensure_ascii=False), encoding="utf-8")
    return lyrics


def _from_yandex(result: Result, token: str) -> Lyrics | None:
    client = sources._client(token)
    for fmt in ("LRC", "TEXT"):
        try:
            track_lyrics = sources._yandex(
                lambda fmt=fmt: client.tracks_lyrics(result.track_id, format_=fmt)
            )
        except Exception as exc:
            if "not-found" in str(exc).lower() or "NotFound" in type(exc).__name__:
                continue
            raise
        if track_lyrics is None:
            continue
        text = sources._yandex(track_lyrics.fetch_lyrics) or ""
        lines = parse_lrc(text) if fmt == "LRC" else _plain(text)
        if lines:
            return Lyrics(lines=lines, synced=fmt == "LRC", source="Яндекс Музыка")
    return None


def _get_json(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": "QuantisMobile (beta)"})
    with urllib.request.urlopen(request, timeout=_TIMEOUT, context=art._ssl_context()) as r:
        return json.loads(r.read().decode("utf-8"))


def _artist_title(result: Result) -> tuple[str, str]:
    """У видео YouTube «Исполнитель - Название» часто в самом названии."""
    title = _TITLE_NOISE.sub("", result.title).strip()
    artist = result.artist.removesuffix(" - Topic").removesuffix("VEVO").strip()
    if result.source != YANDEX and " - " in title:
        artist, title = (part.strip() for part in title.split(" - ", 1))
    return artist, title


def _lyrics_from_item(item: dict) -> Lyrics | None:
    if item.get("syncedLyrics"):
        lines = parse_lrc(item["syncedLyrics"])
        if lines:
            return Lyrics(lines=lines, synced=True, source="LRCLIB")
    if item.get("plainLyrics"):
        return Lyrics(lines=_plain(item["plainLyrics"]), synced=False, source="LRCLIB")
    return None


def _from_lrclib(result: Result) -> Lyrics | None:
    artist, title = _artist_title(result)
    query = {"artist_name": artist, "track_name": title}
    if result.duration:
        query["duration"] = str(result.duration)
    try:
        found = _lyrics_from_item(_get_json(f"{_LRCLIB}/get?{urllib.parse.urlencode(query)}"))
        if found:
            return found
    except Exception as exc:  # 404 — точного совпадения нет, ищем шире
        log.info("lrclib get: %s", exc)
    items = _get_json(
        f"{_LRCLIB}/search?{urllib.parse.urlencode({'q': f'{artist} {title}'.strip()})}"
    )
    # Ближайший по длине, если она известна; синхронный текст — лучше.
    def rank(item: dict) -> tuple:
        gap = abs(float(item.get("duration") or 0) - result.duration) if result.duration else 0
        return (gap > 5, not item.get("syncedLyrics"), gap)

    for item in sorted(items or [], key=rank)[:3]:
        if result.duration and abs(float(item.get("duration") or 0) - result.duration) > 10:
            continue
        found = _lyrics_from_item(item)
        if found:
            return found
    return None
