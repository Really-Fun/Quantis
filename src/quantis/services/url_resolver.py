"""Парсинг ссылок YouTube, Yandex Music и SoundCloud для расширенного поиска."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import parse_qs, urlparse

SourceId = Literal["yandex", "youtube", "soundcloud"]

_YANDEX_TRACK_RE = re.compile(
    r"(?:music\.)?yandex\.(?:ru|com|by|kz|ua)/(?:album/\d+/track/|track/)(\d+)",
    re.IGNORECASE,
)
_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/|music\.youtube\.com/watch\?v=)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)


def detect_source(url: str) -> SourceId | None:
    """Определяет платформу по домену ссылки."""
    text = url.strip()
    lowered = text.lower()
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()

    is_yandex_music_host = host.startswith("music.yandex.")
    if is_yandex_music_host and "/track/" in lowered:
        return "yandex"

    is_youtube_host = (
        host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")
    )
    if is_youtube_host:
        return "youtube"

    if _is_soundcloud_host(host):
        return "soundcloud"
    return None


def parse_yandex_track_id(url: str) -> str | None:
    match = _YANDEX_TRACK_RE.search(url.strip())
    return match.group(1) if match else None


_YOUTUBE_ID_EXACT_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def is_youtube_video_id(value: str) -> bool:
    return bool(_YOUTUBE_ID_EXACT_RE.match(str(value).strip()))


def parse_youtube_video_id(url: str) -> str | None:
    text = url.strip()
    match = _YOUTUBE_ID_RE.search(text)
    if match:
        return match.group(1)
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    is_youtube_host = (
        host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")
    )
    if is_youtube_host:
        query_id = parse_qs(parsed.query).get("v", [None])[0]
        if query_id and len(query_id) == 11:
            return query_id
    return None


def is_soundcloud_host(host: str) -> bool:
    if not host:
        return False
    if host.startswith("www."):
        host = host[4:]
    return (
        host
        in (
            "soundcloud.com",
            "m.soundcloud.com",
            "on.soundcloud.com",
            "api.soundcloud.com",
        )
        or host.endswith(".soundcloud.com")
        or host.endswith("soundcloud.app.goo.gl")
        or host == "soundcloud.app.goo.gl"
    )


def _is_soundcloud_host(host: str) -> bool:
    return is_soundcloud_host(host)


def parse_soundcloud_track_id(url: str) -> str | None:
    """Permalink, числовой API id или исходный URL короткой ссылки."""
    text = url.strip()
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not _is_soundcloud_host(host):
        return None

    if host in ("on.soundcloud.com", "soundcloud.app.goo.gl") or host.endswith(
        "soundcloud.app.goo.gl"
    ):
        return text

    path = (parsed.path or "").strip("/")
    if not path:
        return None

    api_match = re.match(r"tracks/(\d+)", path, re.IGNORECASE)
    if api_match:
        return api_match.group(1)

    parts = [part for part in path.split("/") if part]
    if len(parts) < 2:
        return None
    if parts[0] in {"you", "feed", "discover", "stream", "charts", "pages"}:
        return None
    if parts[1] == "sets":
        return None
    return "/".join(parts)


def parse_track_id(url: str) -> tuple[SourceId, str] | None:
    """Извлекает (source, track_id) из ссылки."""
    source = detect_source(url)
    if source == "yandex":
        track_id = parse_yandex_track_id(url)
        return ("yandex", track_id) if track_id else None
    if source == "youtube":
        video_id = parse_youtube_video_id(url)
        return ("youtube", video_id) if video_id else None
    if source == "soundcloud":
        sc_id = parse_soundcloud_track_id(url)
        return ("soundcloud", sc_id) if sc_id else None
    return None
