"""Встроенные теги и обложка в скачанных mp3/m4a (mutagen)."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    TALB,
    TCON,
    TDRC,
    TIT2,
    TPE1,
    TPE2,
    TRCK,
    TXXX,
    ID3NoHeaderError,
)
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

from quantis.services.cover_validate import cover_file_ok

logger = logging.getLogger(__name__)

QUANTIS_SOURCE_KEY = "QUANTIS_SOURCE"
QUANTIS_ID_KEY = "QUANTIS_ID"

_MP4_FREEFORM_PREFIX = "----:com.quantis:"
_JPEG_MAGIC = b"\xff\xd8"
_PNG_MAGIC = b"\x89PNG"


@dataclass
class TrackMeta:
    source: str
    track_id: str
    title: str
    artist: str
    album: str = ""
    album_artist: str = ""
    year: int | None = None
    genre: str = ""
    track_number: int | None = None
    source_url: str = ""
    # Сырое название от сервиса (миграция): проверка неоднозначных имён.
    # В теги не пишется.
    service_title: str = ""


@dataclass(frozen=True)
class TagIdentity:
    source: str
    track_id: str
    title: str
    artist: str


class TagWriteError(Exception):
    """Не удалось записать теги в файл (оригинал остаётся нетронутым)."""


def source_url(source: str, track_id: str) -> str:
    """Ссылка на трек в источнике; пустая строка, если источник неизвестен."""
    if source == "yandex":
        return f"https://music.yandex.ru/track/{track_id}"
    if source == "youtube":
        return f"https://music.youtube.com/watch?v={track_id}"
    if source == "soundcloud":
        import quantis.models.track  # noqa: F401  (порядок импорта: цикл soundcloud <-> path_provider)
        from quantis.services.soundcloud import watch_url

        return watch_url(track_id)
    return ""


def _cover_data(cover: Path | None) -> tuple[bytes, str] | None:
    """Байты и mime обложки (jpeg/png) или None, если файла нет/он битый."""
    if cover is None or not cover_file_ok(cover):
        return None
    try:
        data = Path(cover).read_bytes()
    except OSError:
        return None
    if data[:2] == _JPEG_MAGIC:
        return data, "image/jpeg"
    if data[:4] == _PNG_MAGIC:
        return data, "image/png"
    return None


def _write_mp3(part: Path, meta: TrackMeta, cover: tuple[bytes, str] | None) -> None:
    try:
        tags = ID3(part)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall(f"TXXX:{QUANTIS_SOURCE_KEY}")
    tags.delall(f"TXXX:{QUANTIS_ID_KEY}")
    tags.add(TXXX(encoding=3, desc=QUANTIS_SOURCE_KEY, text=[meta.source]))
    tags.add(TXXX(encoding=3, desc=QUANTIS_ID_KEY, text=[str(meta.track_id)]))
    text_frames = (
        ("TIT2", TIT2, meta.title),
        ("TPE1", TPE1, meta.artist),
        ("TALB", TALB, meta.album),
        ("TPE2", TPE2, meta.album_artist),
        ("TCON", TCON, meta.genre),
    )
    for key, frame, value in text_frames:
        if value:
            tags.setall(key, [frame(encoding=3, text=[value])])
    if meta.track_number:
        tags.setall("TRCK", [TRCK(encoding=3, text=[str(meta.track_number)])])
    if meta.year:
        tags.delall("TYER")
        tags.setall("TDRC", [TDRC(encoding=3, text=[str(meta.year)])])
    if meta.source_url:
        tags.setall(
            "COMM", [COMM(encoding=3, lang="eng", desc="", text=[meta.source_url])]
        )
    if cover is not None:
        data, mime = cover
        tags.setall(
            "APIC", [APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data)]
        )
    tags.save(part, v2_version=3)


def _ff(value: str) -> MP4FreeForm:
    return MP4FreeForm(value.encode("utf-8"))


def _write_m4a(part: Path, meta: TrackMeta, cover: tuple[bytes, str] | None) -> None:
    audio = MP4(part)
    if audio.tags is None:
        audio.add_tags()
    tags = audio.tags
    tags[_MP4_FREEFORM_PREFIX + QUANTIS_SOURCE_KEY] = [_ff(meta.source)]
    tags[_MP4_FREEFORM_PREFIX + QUANTIS_ID_KEY] = [_ff(str(meta.track_id))]
    for key, value in (
        ("\xa9nam", meta.title),
        ("\xa9ART", meta.artist),
        ("\xa9alb", meta.album),
        ("aART", meta.album_artist),
        ("\xa9gen", meta.genre),
        ("\xa9cmt", meta.source_url),
    ):
        if value:
            tags[key] = [value]
    if meta.year:
        tags["\xa9day"] = [str(meta.year)]
    if meta.track_number:
        tags["trkn"] = [(meta.track_number, 0)]
    if cover is not None:
        data, mime = cover
        fmt = MP4Cover.FORMAT_PNG if mime == "image/png" else MP4Cover.FORMAT_JPEG
        tags["covr"] = [MP4Cover(data, imageformat=fmt)]
    audio.save()


def write_tags(path: Path, meta: TrackMeta, cover: Path | None) -> None:
    """Атомарно пишет теги и обложку: копия *.part -> теги -> replace."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".mp3":
        writer = _write_mp3
    elif suffix == ".m4a":
        writer = _write_m4a
    else:
        raise TagWriteError(f"Неподдерживаемый формат: {suffix or path.name}")
    part = path.with_name(path.name + ".part")
    try:
        shutil.copy2(path, part)
        writer(part, meta, _cover_data(cover))
        part.replace(path)
    except Exception as exc:
        part.unlink(missing_ok=True)
        raise TagWriteError(f"Не удалось записать теги в {path.name}: {exc}") from exc


def _first(values) -> str:
    if not values:
        return ""
    value = values[0]
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def _txxx(tags: ID3, desc: str) -> str:
    frame = tags.get(f"TXXX:{desc}")
    return _first(frame.text) if frame is not None else ""


def read_identity(path: Path) -> TagIdentity | None:
    """Служебные теги Quantis или None (файл без них/нечитаемый). Не бросает."""
    try:
        path = Path(path)
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            tags = ID3(path)
            source = _txxx(tags, QUANTIS_SOURCE_KEY)
            track_id = _txxx(tags, QUANTIS_ID_KEY)
            title = _first(tags["TIT2"].text) if "TIT2" in tags else ""
            artist = _first(tags["TPE1"].text) if "TPE1" in tags else ""
        elif suffix == ".m4a":
            tags = MP4(path).tags or {}
            source = _first(tags.get(_MP4_FREEFORM_PREFIX + QUANTIS_SOURCE_KEY))
            track_id = _first(tags.get(_MP4_FREEFORM_PREFIX + QUANTIS_ID_KEY))
            title = _first(tags.get("\xa9nam"))
            artist = _first(tags.get("\xa9ART"))
        else:
            return None
        if not source or not track_id:
            return None
        return TagIdentity(source, track_id, title, artist)
    except Exception:
        logger.debug("read_identity failed for %s", path, exc_info=True)
        return None
