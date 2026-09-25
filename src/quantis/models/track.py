"""Модель трека

Классы:
1. TrackSource — перечисление платформ
2. Track — базовый дата класс трека
3. YandexTrack — трек ЯндексМузыки
4. YoutubeTrack — трек YouTube
5. SoundCloudTrack — трек SoundCloud
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


def seconds_to_ms(value: object) -> int:
    """Секунды (int/float/str) → миллисекунды. Мусор даёт 0."""
    try:
        sec = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    if sec <= 0:
        return 0
    return int(sec * 1000)


def clock_to_ms(text: object) -> int:
    """'3:21' / '1:02:03' → миллисекунды."""
    raw = str(text or "").strip()
    if not raw or ":" not in raw:
        return 0
    parts = raw.split(":")
    if not all(p.isdigit() for p in parts):
        return 0
    nums = [int(p) for p in parts]
    if len(nums) == 2:
        return (nums[0] * 60 + nums[1]) * 1000
    if len(nums) == 3:
        return (nums[0] * 3600 + nums[1] * 60 + nums[2]) * 1000
    return 0


# YouTube Music в выдаче на русском отдаёт счётчик лайков/просмотров как ещё
# одного «исполнителя»: «37R, Отметок "Нравится": 1,2 тыс.». В имени скачанного
# файла кавычки и двоеточие уже заменены на «_».
_ARTIST_SEPARATOR = re.compile(r"(,\s+|\s+\|\s+|\s+•\s+)")
_STAT_WORD = re.compile(
    r"нравится|просмотр|отмет(?:ок|ки|ка)|подписчик|\bviews?\b|\blikes?\b|\bsubscribers?\b",
    re.IGNORECASE,
)


def _is_stat_text(segment: str) -> bool:
    return any(ch.isdigit() for ch in segment) and bool(_STAT_WORD.search(segment))


def strip_youtube_stats(author: str) -> str:
    """Убирает из строки исполнителя счётчики лайков и просмотров YouTube."""
    parts = _ARTIST_SEPARATOR.split(author)
    kept: list[str] = []
    for index in range(0, len(parts), 2):
        segment = parts[index]
        if not segment.strip() or _is_stat_text(segment):
            continue
        if kept:
            kept.append(parts[index - 1])
        kept.append(segment)
    return "".join(kept).strip() or author


class TrackSource(StrEnum):
    """Перечисление поддерживаемых платформ.

    Используется вместо строк ``"yandex"`` / ``"youtube"`` / ``"soundcloud"``
    по всему коду.
    Совместимо со строками: ``TrackSource.YANDEX == "yandex"`` → ``True``.
    """

    YANDEX = "yandex"
    YOUTUBE = "youtube"
    SOUNDCLOUD = "soundcloud"


@dataclass(eq=False)
class Track:
    """Базовый дата класс трека."""

    track_id: int | str
    title: str
    author: str
    downloaded: bool = False
    source: str = ""
    listen_count: int = 0
    duration_ms: int = 0

    def __repr__(self) -> str:
        return f"{self.source}:{self.track_id}"

    def __str__(self) -> str:
        return f"{self.source} : {self.title} - {self.author}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Track):
            return False
        return str(self.source) == str(other.source) and str(self.track_id) == str(
            other.track_id
        )

    def __hash__(self) -> int:
        return hash((str(self.source), str(self.track_id)))


@dataclass(eq=False)
class YandexTrack(Track):
    """Трек Яндекс.Музыки"""

    source: str = TrackSource.YANDEX


@dataclass(eq=False)
class YoutubeTrack(Track):
    """Трек YouTube"""

    source: str = TrackSource.YOUTUBE
    extension: str = "m4a"

    def __post_init__(self) -> None:
        self.author = strip_youtube_stats(self.author)


@dataclass(eq=False)
class SoundCloudTrack(Track):
    """Трек SoundCloud"""

    source: str = TrackSource.SOUNDCLOUD
    extension: str = "mp3"
    thumbnail_url: str = ""
