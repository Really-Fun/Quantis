"""Политика видео-фона: стримим любой длины, на диск — только короткие клипы."""

from __future__ import annotations

# Часовой mp4 в кэш не качаем: это сотни МБ, стрима хватает.
WALLPAPER_CACHE_MAX_SEC = 15 * 60
WALLPAPER_MAX_LOCAL_BYTES = 40 * 1024 * 1024
WALLPAPER_QUALITY_CHOICES = (360, 480, 720, 1080)
WALLPAPER_FPS_CHOICES = (5, 10, 15, 24, 30, 60)
WALLPAPER_DEFAULT_QUALITY = 360
WALLPAPER_DEFAULT_FPS = 10
# Звук слышно позже, чем его позиция в плеере: буфер Qt + PipeWire/WASAPI.
# На столько видео держим позади позиции звука. Картинка такой задержки нет.
WALLPAPER_DEFAULT_AV_DELAY_MS = 250
WALLPAPER_AV_DELAY_MIN_MS = -500
WALLPAPER_AV_DELAY_MAX_MS = 1000
_DECODE_MAX_SIDE = {360: 640, 480: 854, 720: 1280, 1080: 1920}
_FORMAT_FALLBACK_HEIGHT = {360: 480, 480: 720, 720: 1080, 1080: 1080}


def should_play_local_wallpaper(size_bytes: int) -> bool:
    return 0 < size_bytes <= WALLPAPER_MAX_LOCAL_BYTES


def should_fetch_wallpaper_now(*, local: bool, audio_live: bool) -> bool:
    """Локальный клип — сразу. Remote yt-dlp не должен обгонять старт аудио."""
    return bool(local or audio_live)


def wallpaper_can_apply_seek(*, duration_ms: int, media_ready: bool) -> bool:
    """Без duration setPosition на googlevideo срывает декод — остаётся обложка."""
    _ = media_ready
    return int(duration_ms) > 0


def wallpaper_seek_target(position_ms: int, duration_ms: int) -> int:
    position = max(0, int(position_ms))
    duration = int(duration_ms)
    if duration > 400:
        return min(position, max(0, duration - 400))
    return position


def wallpaper_duration_filter(info: dict, *, incomplete: bool = False) -> str | None:
    """Фильтр yt-dlp: не качать час видео в кэш обоев."""
    duration = int(info.get("duration") or 0)
    if duration > WALLPAPER_CACHE_MAX_SEC:
        return f"too long for wallpaper cache ({duration}s)"
    return None


def clamp_wallpaper_quality(value: int) -> int:
    if value in WALLPAPER_QUALITY_CHOICES:
        return value
    return min(WALLPAPER_QUALITY_CHOICES, key=lambda height: abs(height - value))


def clamp_wallpaper_fps(value: int) -> int:
    if value in WALLPAPER_FPS_CHOICES:
        return value
    return min(WALLPAPER_FPS_CHOICES, key=lambda fps: abs(fps - value))


def clamp_wallpaper_av_delay(value: int) -> int:
    return max(WALLPAPER_AV_DELAY_MIN_MS, min(WALLPAPER_AV_DELAY_MAX_MS, int(value)))


def wallpaper_decode_max_side(height: int) -> int:
    return _DECODE_MAX_SIDE[clamp_wallpaper_quality(height)]


def wallpaper_yt_dlp_format(height: int) -> str:
    h = clamp_wallpaper_quality(height)
    extra = _FORMAT_FALLBACK_HEIGHT[h]
    return (
        f"bestvideo[height={h}][vcodec^=avc1][protocol=https]/"
        f"bestvideo[height={h}][ext=mp4][protocol=https]/"
        f"bestvideo[height={h}][protocol=https]/"
        f"bestvideo[height<={h}][vcodec^=avc1][protocol=https]/"
        f"bestvideo[height<={h}][ext=mp4][protocol=https]/"
        f"bestvideo[height<={h}][protocol=https]/"
        f"best[height<={h}][vcodec!=none][acodec=none]/"
        f"best[height<={extra}][vcodec!=none][acodec=none]/"
        f"bestvideo/"
        f"best"
    )


def wallpaper_yt_dlp_android_format(height: int) -> str:
    return wallpaper_yt_dlp_format(height)


def wallpaper_url_itag(url: str | None) -> str | None:
    """itag из googlevideo URL — чтобы фон не брал тот же поток, что и звук."""
    raw = (url or "").strip()
    if not raw:
        return None
    from urllib.parse import parse_qs, urlparse

    values = parse_qs(urlparse(raw).query).get("itag") or []
    itag = str(values[0]).strip() if values else ""
    return itag or None


# YouTube itag → заявленное качество. Пиксели часто ниже (640x268 «360p»).
_ITAG_QUALITY = {
    "17": 144,
    "160": 144,
    "278": 144,
    "394": 144,
    "133": 240,
    "242": 240,
    "395": 240,
    "18": 360,
    "134": 360,
    "243": 360,
    "396": 360,
    "59": 480,
    "78": 480,
    "135": 480,
    "244": 480,
    "397": 480,
    "22": 720,
    "136": 720,
    "247": 720,
    "298": 720,
    "398": 720,
    "137": 1080,
    "248": 1080,
    "299": 1080,
    "399": 1080,
    "271": 1440,
    "308": 1440,
    "400": 1440,
    "313": 2160,
    "315": 2160,
    "401": 2160,
}
_MUXED_ITAGS = frozenset({"17", "18", "22", "59", "78"})


def wallpaper_source_has_video(url: str | None) -> bool:
    """Трек уже muxed (itag 18) — второй googlevideo не нужен, кадры есть в плеере."""
    raw = (url or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if "mime=video" in lowered or "mime%3dvideo" in lowered:
        return True
    return wallpaper_url_itag(raw) in _MUXED_ITAGS


def wallpaper_muxed_height(url: str | None) -> int | None:
    itag = wallpaper_url_itag(url)
    if not itag or itag not in _MUXED_ITAGS:
        return None
    return _ITAG_QUALITY.get(itag)


def wallpaper_format_quality(
    *, itag: str | None = None, width: int = 0, height: int = 0
) -> int:
    """Класс качества потока: itag 136 = 720p, даже если кадр 1280x534."""
    known = _ITAG_QUALITY.get(str(itag or "").strip())
    if known:
        return known
    width = int(width or 0)
    height = int(height or 0)
    side = max(width, height)
    if height >= 1080 or side >= 1920:
        return 1080
    if height >= 720 or side >= 1280:
        return 720
    if height >= 480 or side >= 854:
        return 480
    if height >= 360 or side >= 640:
        return 360
    return height


def wallpaper_source_meets_quality(url: str | None, height: int) -> bool:
    """Следовать за аудио-плеером только если его кадры не хуже выбранного качества."""
    if not wallpaper_source_has_video(url):
        return False
    known = wallpaper_muxed_height(url)
    if known is None:
        return False
    return known >= clamp_wallpaper_quality(height)


def wallpaper_stream_conflicts(audio_url: str | None, video_url: str | None) -> bool:
    """Второй QMediaPlayer на тот же googlevideo itag рвёт звук и крутит трек с нуля."""
    audio = (audio_url or "").strip()
    video = (video_url or "").strip()
    if not audio or not video:
        return False
    if audio == video:
        return True
    from urllib.parse import parse_qs, urlparse

    audio_parts = urlparse(audio)
    video_parts = urlparse(video)
    if audio_parts.netloc != video_parts.netloc:
        return False
    if "googlevideo.com" not in audio_parts.netloc:
        return False
    audio_q = parse_qs(audio_parts.query)
    video_q = parse_qs(video_parts.query)
    return bool(audio_q.get("id") and audio_q.get("id") == video_q.get("id")) and (
        audio_q.get("itag") == video_q.get("itag")
    )


def wallpaper_cache_format(height: int) -> str:
    h = clamp_wallpaper_quality(height)
    return (
        f"best[ext=mp4][vcodec!=none][height<={h}]/"
        f"best[ext=mp4][height<={h}]/"
        f"18/best[height<={h}]"
    )
