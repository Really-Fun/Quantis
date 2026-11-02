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
_YANDEX_RE = re.compile(r"([0-9]+)_(.*)", re.DOTALL)


@dataclass(frozen=True)
class LegacyName:
    source: str
    track_id: str
    title: str
    author: str


def _from_rest(source: str, track_id: str, rest: str) -> LegacyName:
    title, _, author = rest.partition("_")
    return LegacyName(source, track_id, title, author)


def parse_legacy_name(filename: str) -> LegacyName | None:
    """Разбирает имя старого файла; возвращает None, если имя не в старом формате."""
    stem, ext = os.path.splitext(filename)
    if ext.lower() not in _LEGACY_SUFFIXES:
        return None

    match = _SOUNDCLOUD_RE.fullmatch(stem)
    if match:
        return _from_rest("soundcloud", match.group(1), match.group(2))

    id_end = _YOUTUBE_ID_LENGTH
    if (
        len(stem) > id_end
        and stem[id_end] == "_"
        and is_youtube_video_id(stem[:id_end])
        and not stem[:id_end].isdigit()
    ):
        return _from_rest("youtube", stem[:id_end], stem[id_end + 1 :])

    match = _YANDEX_RE.fullmatch(stem)
    if match:
        return _from_rest("yandex", match.group(1), match.group(2))

    return None
