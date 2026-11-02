"""Разбор имён скачанных файлов старого формата `ID_Название_Исполнитель.ext`."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from quantis.services.url_resolver import is_youtube_video_id

_LEGACY_SUFFIXES = frozenset({".mp3", ".m4a"})
# Совпадает с quantis.services.soundcloud.SOUNDCLOUD_FILE_PREFIX; не импортируем,
# чтобы не усугублять циклический импорт soundcloud <-> providers.path_provider.
_SOUNDCLOUD_PREFIX = "sc"
_YOUTUBE_ID_LENGTH = 11
_SOUNDCLOUD_RE = re.compile(r"sc([0-9]+)_(.*)", re.DOTALL)
_DIGITS_RE = re.compile(r"[0-9]+")


@dataclass(frozen=True)
class LegacyName:
    source: str
    track_id: str
    title: str
    author: str


def _from_rest(source: str, track_id: str, rest: str) -> LegacyName:
    parts = rest.split("_", 1)
    title = parts[0]
    author = parts[1] if len(parts) > 1 else ""
    return LegacyName(source, track_id, title, author)


def parse_legacy_names(filename: str) -> list[LegacyName]:
    """Возвращает все допустимые прочтения имени файла (yandex раньше youtube).

    Пустой список — имя не в старом формате. Одно имя может читаться и как
    yandex, и как youtube (например, `12345678_Ab_Song.mp3`).
    """
    stem, ext = os.path.splitext(filename)
    if ext.lower() not in _LEGACY_SUFFIXES:
        return []

    match = _SOUNDCLOUD_RE.fullmatch(stem)
    if match:
        return [_from_rest("soundcloud", match.group(1), match.group(2))]

    readings: list[LegacyName] = []

    prefix, sep, rest = stem.partition("_")
    if sep and _DIGITS_RE.fullmatch(prefix):
        readings.append(_from_rest("yandex", prefix, rest))

    id_end = _YOUTUBE_ID_LENGTH
    candidate = stem[:id_end]
    if (
        len(stem) > id_end
        and stem[id_end] == "_"
        and is_youtube_video_id(candidate)
        and not candidate.isdigit()
    ):
        readings.append(_from_rest("youtube", candidate, stem[id_end + 1 :]))

    return readings


def parse_legacy_name(filename: str) -> LegacyName | None:
    """Единственное прочтение имени файла; None, если их нет или больше одного."""
    readings = parse_legacy_names(filename)
    return readings[0] if len(readings) == 1 else None
