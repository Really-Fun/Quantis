"""Политика видео-фона: стримим любой длины, на диск — только короткие клипы."""

from __future__ import annotations

# Часовой mp4 в кэш не качаем: это сотни МБ, стрима хватает.
WALLPAPER_CACHE_MAX_SEC = 15 * 60
WALLPAPER_MAX_LOCAL_BYTES = 40 * 1024 * 1024
WALLPAPER_SYNC_INTERVAL_MS = 1200
WALLPAPER_SYNC_DRIFT_MS = 1500
# Если видео стабильно не догоняет, порог растёт: лучше лёгкий рассинхрон,
# чем перемотка HTTP-потока каждую секунду.
WALLPAPER_MAX_DRIFT_MS = 6000
WALLPAPER_QUALITY_CHOICES = (360, 480, 720)
WALLPAPER_FPS_CHOICES = (5, 10, 15, 24, 30)
WALLPAPER_DEFAULT_QUALITY = 360
WALLPAPER_DEFAULT_FPS = 10
_DECODE_MAX_SIDE = {360: 640, 480: 854, 720: 1280}
_FORMAT_FALLBACK_HEIGHT = {360: 480, 480: 720, 720: 720}


def should_play_local_wallpaper(size_bytes: int) -> bool:
    return 0 < size_bytes <= WALLPAPER_MAX_LOCAL_BYTES


def should_fetch_wallpaper_now(*, local: bool, audio_live: bool) -> bool:
    """Локальный клип — сразу. Remote yt-dlp не должен обгонять старт аудио."""
    return bool(local or audio_live)


def wallpaper_positions_drifted(
    audio_ms: int, video_ms: int, *, tolerance_ms: int = WALLPAPER_SYNC_DRIFT_MS
) -> bool:
    if audio_ms <= 0 or video_ms < 0:
        return False
    return abs(audio_ms - video_ms) > max(WALLPAPER_SYNC_DRIFT_MS, tolerance_ms)


def wallpaper_next_drift_tolerance(current_ms: int) -> int:
    return min(WALLPAPER_MAX_DRIFT_MS, max(WALLPAPER_SYNC_DRIFT_MS, current_ms) * 2)


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


def wallpaper_decode_max_side(height: int) -> int:
    return _DECODE_MAX_SIDE[clamp_wallpaper_quality(height)]


def wallpaper_yt_dlp_format(height: int) -> str:
    h = clamp_wallpaper_quality(height)
    extra = _FORMAT_FALLBACK_HEIGHT[h]
    return (
        f"bestvideo[height<={h}][protocol^=http]/"
        f"best[height<={h}][vcodec!=none][acodec=none]/"
        f"best[height<={h}][vcodec!=none]/"
        f"best[height<={extra}][vcodec!=none]/"
        f"18"
    )


def wallpaper_yt_dlp_android_format(height: int) -> str:
    return wallpaper_yt_dlp_format(height)


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
