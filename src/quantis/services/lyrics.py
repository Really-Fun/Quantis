"""Тексты песен: Яндекс Музыка (для её треков), иначе открытая база lrclib.net.

Перенос ``mobile/lyrics.py`` на асинхронный стек десктопа. Ответ — ``Lyrics``:
строки с временем (LRC, синхронный текст) или без него. Найденное и
«не нашлось» кладутся в кэш на диске, чтобы второй раз — и без сети — не
спрашивать.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import aiohttp

from quantis.models.track import Track, TrackSource
from quantis.utils import app_paths

logger = logging.getLogger(__name__)

_LRCLIB = "https://lrclib.net/api"
_TIMEOUT = aiohttp.ClientTimeout(total=15)
_HEADERS = {"User-Agent": "Quantis (https://github.com/ReallyFun/Quantis)"}
_LRC_LINE = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")
# Хвосты названий с YouTube, мешающие поиску: (Official Video), [Lyrics]…
_TITLE_NOISE = re.compile(
    r"\s*[\(\[][^)\]]*(official|video|audio|lyric|клип|mv|hd|4k|visualizer)"
    r"[^)\]]*[\)\]]",
    re.I,
)


@dataclass
class LyricLine:
    t: int
    """Начало строки в мс; -1 — у несинхронного текста."""
    text: str


@dataclass
class Lyrics:
    lines: list[LyricLine] = field(default_factory=list)
    synced: bool = False
    source: str = ""
    """«Яндекс Музыка», «LRCLIB» или "" — не нашлось."""

    def line_at(self, position_ms: int) -> int:
        """Индекс строки, которая звучит на ``position_ms`` (-1 — ещё ни одной)."""
        if not self.synced:
            return -1
        current = -1
        for index, line in enumerate(self.lines):
            if line.t > position_ms:
                break
            current = index
        return current


def parse_lrc(text: str) -> list[LyricLine]:
    """``[мм:сс.хх] строка`` → строки по времени."""
    lines: list[LyricLine] = []
    for raw in text.splitlines():
        stamps = list(_LRC_LINE.finditer(raw))
        if not stamps:
            continue
        words = raw[stamps[-1].end() :].strip()
        for stamp in stamps:  # «[00:10][01:20] припев» — две строки
            seconds = float(stamp.group(2).replace(":", "."))
            ms = int((int(stamp.group(1)) * 60 + seconds) * 1000)
            lines.append(LyricLine(ms, words))
    return sorted(lines, key=lambda line: line.t)


def _plain(text: str) -> list[LyricLine]:
    return [LyricLine(-1, line.strip()) for line in text.strip().splitlines()]


def artist_title(track: Track) -> tuple[str, str]:
    """У видео YouTube «Исполнитель - Название» часто в самом названии."""
    title = _TITLE_NOISE.sub("", track.title).strip()
    artist = track.author.removesuffix(" - Topic").removesuffix("VEVO").strip()
    if str(track.source) != TrackSource.YANDEX and " - " in title:
        artist, title = (part.strip() for part in title.split(" - ", 1))
    return artist, title


# ------------------------------------------------------------------ cache


def _cache_path(track: Track) -> Path:
    folder = app_paths.cache_dir() / "lyrics"
    folder.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(f"{track.source}:{track.track_id}".encode()).hexdigest()
    return folder / f"{key}.json"


def cached(track: Track) -> Lyrics | None:
    try:
        raw = json.loads(_cache_path(track).read_text(encoding="utf-8"))
        lines = [LyricLine(int(line["t"]), str(line["text"])) for line in raw["lines"]]
        return Lyrics(lines, bool(raw.get("synced")), str(raw.get("source", "")))
    except (OSError, ValueError, TypeError, KeyError):
        return None


def _store(track: Track, lyrics: Lyrics) -> None:
    try:
        _cache_path(track).write_text(
            json.dumps(asdict(lyrics), ensure_ascii=False), encoding="utf-8"
        )
    except OSError:
        logger.warning("Не удалось сохранить текст в кэш", exc_info=True)


# ------------------------------------------------------------------ fetch


class LyricsService:
    """Текст трека: из кэша, иначе из сети (и в кэш)."""

    async def fetch(self, track: Track) -> Lyrics:
        found = cached(track)
        if found is not None:
            return found
        result: Lyrics | None = None
        if str(track.source) == TrackSource.YANDEX:
            try:
                result = await self._from_yandex(track)
            except Exception as exc:  # нет текста или прав — попробуем lrclib
                logger.info("Текст из Яндекса не получен: %s", exc)
        if result is None:
            try:
                result = await self._from_lrclib(track)
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                # сеть упала — в кэш «не нашлось» не пишем, спросим ещё раз
                logger.info("lrclib недоступен: %s", exc)
                return Lyrics()
        lyrics = result or Lyrics()
        _store(track, lyrics)
        return lyrics

    async def _from_yandex(self, track: Track) -> Lyrics | None:
        from quantis.config.clients import Clients
        from quantis.config.credentials import yandex_token

        if not yandex_token():
            return None
        client = Clients().get_yandex_client()
        if client is None:
            return None
        for fmt in ("LRC", "TEXT"):
            try:
                track_lyrics = await client.tracks_lyrics(track.track_id, format_=fmt)
            except Exception as exc:
                if "not-found" in str(exc).lower() or "NotFound" in type(exc).__name__:
                    continue
                raise
            if track_lyrics is None:
                continue
            text = await track_lyrics.fetch_lyrics_async() or ""
            lines = parse_lrc(text) if fmt == "LRC" else _plain(text)
            if lines:
                return Lyrics(lines, fmt == "LRC", "Яндекс Музыка")
        return None

    async def _from_lrclib(self, track: Track) -> Lyrics | None:
        artist, title = artist_title(track)
        duration = (track.duration_ms or 0) / 1000
        query = {"artist_name": artist, "track_name": title}
        if duration:
            query["duration"] = str(round(duration))
        async with aiohttp.ClientSession(timeout=_TIMEOUT, headers=_HEADERS) as http:
            async with http.get(f"{_LRCLIB}/get", params=query) as response:
                if response.status == 200:
                    found = _lyrics_from_item(await response.json())
                    if found:
                        return found
            # точного совпадения нет — ищем шире
            params = {"q": f"{artist} {title}".strip()}
            async with http.get(f"{_LRCLIB}/search", params=params) as response:
                response.raise_for_status()
                items = await response.json()
        return pick_search_result(items or [], duration)


def _lyrics_from_item(item: dict) -> Lyrics | None:
    if item.get("syncedLyrics"):
        lines = parse_lrc(item["syncedLyrics"])
        if lines:
            return Lyrics(lines, True, "LRCLIB")
    if item.get("plainLyrics"):
        return Lyrics(_plain(item["plainLyrics"]), False, "LRCLIB")
    return None


def pick_search_result(items: list[dict], duration: float) -> Lyrics | None:
    """Ближайший по длине (если она известна); синхронный текст — лучше."""

    def gap(item: dict) -> float:
        return abs(float(item.get("duration") or 0) - duration) if duration else 0.0

    def rank(item: dict) -> tuple:
        return (gap(item) > 5, not item.get("syncedLyrics"), gap(item))

    for item in sorted(items, key=rank)[:3]:
        if duration and gap(item) > 10:
            continue
        found = _lyrics_from_item(item)
        if found:
            return found
    return None
