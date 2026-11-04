"""Общие хелперы SoundCloud (URL, разбор yt-dlp, файловый префикс)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from quantis.models.track import SoundCloudTrack
from quantis.services.url_resolver import is_soundcloud_host

SOUNDCLOUD_FILE_PREFIX = "sc"

_YDL_COMMON: dict[str, Any] = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "noplaylist": True,
}


def ydl_opts(**extra: Any) -> dict[str, Any]:
    opts = dict(_YDL_COMMON)
    opts.update(extra)
    return opts


def watch_url(track_id: str | int) -> str:
    """Собирает URL, который понимает yt-dlp: permalink, короткая ссылка или API id."""
    text = str(track_id).strip()
    if text.startswith("http://") or text.startswith("https://"):
        host = (urlparse(text).hostname or "").lower()
        if not is_soundcloud_host(host):
            raise ValueError(f"Ожидалась ссылка SoundCloud, получен хост {host!r}")
        if urlparse(text).scheme not in ("http", "https"):
            raise ValueError("Недопустимая схема ссылки SoundCloud")
        return text
    if "/" in text:
        return f"https://soundcloud.com/{text.lstrip('/')}"
    return f"https://api.soundcloud.com/tracks/{text}"


def storage_id(track_id: str | int, source: str = "soundcloud") -> str:
    """Идентификатор в имени файла. Префикс sc, чтобы не пересекаться с Яндексом."""
    tid = str(track_id).strip()
    if str(source).lower() != "soundcloud":
        return tid
    prefix = SOUNDCLOUD_FILE_PREFIX
    if tid.startswith(prefix) and tid[len(prefix) :].isdigit():
        return tid
    if tid.isdigit():
        return f"{SOUNDCLOUD_FILE_PREFIX}{tid}"
    return f"{SOUNDCLOUD_FILE_PREFIX}{tid}"


def parse_storage_id(file_stem_id: str) -> str | None:
    """Из `sc12345` в имени файла возвращает числовой id, иначе None."""
    if not file_stem_id.startswith(SOUNDCLOUD_FILE_PREFIX):
        return None
    raw = file_stem_id[len(SOUNDCLOUD_FILE_PREFIX) :]
    return raw if raw.isdigit() else None


def track_from_ydl(info: dict[str, Any] | None) -> SoundCloudTrack | None:
    if not info:
        return None
    track_id = info.get("id")
    if not track_id:
        return None
    title = str(info.get("title") or info.get("fulltitle") or "")
    author = (
        info.get("artist")
        or info.get("uploader")
        or info.get("creator")
        or info.get("uploader_id")
        or "Unknown Artist"
    )
    thumbnail = str(info.get("thumbnail") or "")
    if not thumbnail:
        thumbs = info.get("thumbnails") or []
        if thumbs:
            thumbnail = str(thumbs[-1].get("url") or "")
    duration_sec = info.get("duration")
    duration_ms = 0
    try:
        if duration_sec:
            duration_ms = max(0, int(float(duration_sec) * 1000))
    except (TypeError, ValueError):
        duration_ms = 0
    return SoundCloudTrack(
        track_id=str(track_id),
        title=title,
        author=str(author),
        downloaded=False,
        thumbnail_url=thumbnail,
        duration_ms=duration_ms,
    )


def _api_playable(item: dict[str, Any]) -> bool:
    """Есть ли поток без DRM (cbc/ctr-encrypted-hls не сыграть)."""
    transcodings = (item.get("media") or {}).get("transcodings") or []
    if not transcodings:
        return True  # не знаем — пусть решит воспроизведение
    return any(
        "encrypted" not in str((t.get("format") or {}).get("protocol") or "")
        for t in transcodings
    )


def track_from_api(item: dict[str, Any] | None) -> SoundCloudTrack | None:
    """Трек из ответа api-v2 search/tracks; заблокированные и DRM — None."""
    if not isinstance(item, dict):
        return None
    track_id = str(item.get("id") or "")
    if item.get("kind") != "track" or not track_id.isdigit():
        return None
    if item.get("policy") == "BLOCK" or not _api_playable(item):
        return None
    user = item.get("user") or {}
    art = str(item.get("artwork_url") or user.get("avatar_url") or "")
    if art.startswith("https://"):
        art = art.replace("-large.", "-t500x500.")
    else:
        art = ""
    try:
        duration_ms = max(
            0, int(item.get("full_duration") or item.get("duration") or 0)
        )
    except (TypeError, ValueError):
        duration_ms = 0
    return SoundCloudTrack(
        track_id=track_id,
        title=str(item.get("title") or track_id),
        author=str(user.get("username") or "Unknown Artist"),
        downloaded=False,
        thumbnail_url=art,
        duration_ms=duration_ms,
    )
