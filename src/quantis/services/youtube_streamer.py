"""YouTube streaming via yt-dlp."""

from __future__ import annotations

import logging
from asyncio import get_running_loop
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import monotonic
from typing import Any

from quantis.models import Track
from quantis.models.track import seconds_to_ms
from quantis.services.wallpaper_policy import (
    WALLPAPER_DEFAULT_QUALITY,
    clamp_wallpaper_quality,
    wallpaper_yt_dlp_android_format,
    wallpaper_yt_dlp_format,
)
from quantis.services.yandex_streamer import AsyncStreamerInterface

logger = logging.getLogger(__name__)

_INFO_CACHE_TTL_SEC = 90.0
_INFO_CACHE_MAX = 8
_SLIM_FORMAT_KEYS = (
    "url",
    "protocol",
    "ext",
    "format_id",
    "vcodec",
    "acodec",
    "abr",
    "tbr",
    "height",
)
_SLIM_INFO_KEYS = ("url", "protocol", "ext", "format_id", "vcodec", "acodec")


def _slim_format(fmt: dict[str, Any]) -> dict[str, Any]:
    return {key: fmt[key] for key in _SLIM_FORMAT_KEYS if key in fmt}


def slim_youtube_info(info: dict[str, Any] | None) -> dict[str, Any] | None:
    """Оставляет только поля для выбора URL. extract_info весит мегабайты."""
    if not info:
        return None
    formats = [
        _slim_format(fmt)
        for fmt in (info.get("formats") or [])
        if AsyncYoutubeStreamer._is_playable_format(fmt)
    ]
    slim: dict[str, Any] = {
        "duration": info.get("duration"),
        "formats": formats,
    }
    for key in _SLIM_INFO_KEYS:
        if key in info:
            slim[key] = info[key]
    return slim


class AsyncYoutubeStreamer(AsyncStreamerInterface):
    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._common = {
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "quiet": True,
            "noplaylist": True,
            "extract_flat": False,
            "no_warnings": True,
            "postprocessors": [],
            "skip_download": True,
            "ignore_no_formats_error": True,
            "socket_timeout": 8,
            "retries": 0,
        }
        self._executor = executor
        self._info_lock = Lock()
        self._info_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def invalidate(self, track_id: str) -> None:
        with self._info_lock:
            self._info_cache.pop(str(track_id), None)

    def clear_cache(self) -> None:
        with self._info_lock:
            self._info_cache.clear()

    def _cached_info(self, track_id: str) -> dict[str, Any] | None:
        key = str(track_id)
        now = monotonic()
        with self._info_lock:
            hit = self._info_cache.get(key)
            if hit is None:
                return None
            stamped, info = hit
            if now - stamped > _INFO_CACHE_TTL_SEC:
                self._info_cache.pop(key, None)
                return None
            return info

    def _store_info(self, track_id: str, info: dict[str, Any] | None) -> None:
        slim = slim_youtube_info(info)
        if not slim:
            return
        key = str(track_id)
        with self._info_lock:
            self._info_cache[key] = (monotonic(), slim)
            while len(self._info_cache) > _INFO_CACHE_MAX:
                oldest = min(
                    self._info_cache, key=lambda item: self._info_cache[item][0]
                )
                self._info_cache.pop(oldest, None)

    def _attempt_opts(
        self, *, video: bool = False, height: int = WALLPAPER_DEFAULT_QUALITY
    ) -> list[dict]:
        from quantis.config.credentials import youtube_yt_dlp_cookiefile

        cookiefile = youtube_yt_dlp_cookiefile()
        if video:
            height = clamp_wallpaper_quality(height)
        fmt = (
            wallpaper_yt_dlp_format(height)
            if video
            else (
                "ba[protocol=https][ext=m4a]/"
                "ba[protocol=https]/"
                "bestaudio[protocol=https]/"
                "bestaudio"
            )
        )
        android_fmt = (
            wallpaper_yt_dlp_android_format(height) if video else fmt
        )

        def build(
            clients: list[str],
            *,
            format_id: str,
            cookies: bool = False,
            skip_player: bool = True,
        ) -> dict:
            youtube: dict[str, Any] = {
                "player_client": clients,
                "skip": ["hls", "dash", "translated_subs"],
            }
            if skip_player:
                # Innertube android без webpage/player JS — обычно <2с.
                youtube["player_skip"] = ["webpage", "configs"]
            opts: dict[str, Any] = {
                **self._common,
                "format": format_id,
                "extractor_args": {"youtube": youtube},
            }
            if cookies and cookiefile:
                opts["cookiefile"] = cookiefile
            return opts

        attempts: list[dict] = [
            build(["android"], format_id=android_fmt),
        ]
        if cookiefile:
            attempts.append(
                build(
                    ["web", "mweb"],
                    format_id=fmt,
                    cookies=True,
                    skip_player=False,
                )
            )
        else:
            attempts.append(build(["web"], format_id=fmt, skip_player=False))

        return attempts

    @staticmethod
    def _is_playable_format(fmt: dict) -> bool:
        if not fmt.get("url"):
            return False
        protocol = str(fmt.get("protocol") or "").lower()
        if any(
            token in protocol for token in ("m3u8", "dash", "fragment", "ism", "rtmp")
        ):
            return False
        if protocol and not protocol.startswith("http"):
            return False
        if protocol.startswith("mhtml") or protocol == "mhtml":
            return False
        ext = str(fmt.get("ext") or "").lower()
        if ext in ("mhtml", "jpg", "png", "webp"):
            return False
        fid = str(fmt.get("format_id") or "")
        if fid.startswith("sb"):
            return False
        return True

    @staticmethod
    def _duration_ms_from_info(info: dict[str, Any] | None) -> int:
        if not info:
            return 0
        return seconds_to_ms(info.get("duration"))

    @classmethod
    def _pick_stream_url(
        cls,
        info: dict[str, Any] | None,
        *,
        prefer_video: bool = False,
        target_height: int = WALLPAPER_DEFAULT_QUALITY,
    ) -> str | None:
        if not info:
            return None

        formats = [f for f in (info.get("formats") or []) if cls._is_playable_format(f)]
        top_url = info.get("url")
        if top_url and cls._is_playable_format(
            {
                "url": top_url,
                "protocol": info.get("protocol"),
                "ext": info.get("ext"),
                "format_id": info.get("format_id"),
                "vcodec": info.get("vcodec"),
                "acodec": info.get("acodec"),
            }
        ):
            vcodec = str(info.get("vcodec") or "none")
            acodec = str(info.get("acodec") or "none")
            has_audio = acodec not in ("", "none")
            has_video = vcodec not in ("", "none")
            if prefer_video:
                if has_video and not has_audio:
                    return str(top_url)
            elif has_audio and not has_video:
                return str(top_url)

        if not formats:
            return str(top_url) if top_url else None

        def score(fmt: dict) -> tuple:
            vcodec = str(fmt.get("vcodec") or "none")
            acodec = str(fmt.get("acodec") or "none")
            has_audio = acodec not in ("", "none")
            has_video = vcodec not in ("", "none")
            audio_only = has_audio and not has_video
            progressive = has_audio and has_video
            ext = str(fmt.get("ext") or "").lower()
            abr = int(fmt.get("abr") or fmt.get("tbr") or 0)
            height = int(fmt.get("height") or 0)
            if prefer_video:
                video_only = has_video and not has_audio
                return (
                    2 if video_only else (1 if has_video else 0),
                    -abs(height - target_height) if height else -9999,
                    -abr,
                )
            return (
                2 if audio_only else (1 if progressive else 0),
                2 if ext in ("m4a", "mp4") else (1 if ext in ("webm", "opus") else 0),
                abr,
            )

        best = max(formats, key=score)
        return str(best.get("url") or "") or None

    async def get_stream_url(self, track: Track) -> str | None:
        url, duration_ms = await get_running_loop().run_in_executor(
            self._executor, self.sync_stream, track.track_id
        )
        if duration_ms > 0:
            track.duration_ms = duration_ms
        return url

    async def get_video_url(
        self, video_id: str, height: int = WALLPAPER_DEFAULT_QUALITY
    ) -> str | None:
        url, _duration = await self.get_video_info(video_id, height=height)
        return url

    async def get_video_info(
        self, video_id: str, height: int = WALLPAPER_DEFAULT_QUALITY
    ) -> tuple[str | None, int]:
        return await get_running_loop().run_in_executor(
            self._executor, self.sync_video_stream, video_id, height
        )

    def sync_stream(self, track_id: str) -> tuple[str | None, int]:
        from yt_dlp import YoutubeDL

        from quantis.services.url_resolver import is_youtube_video_id

        if not is_youtube_video_id(str(track_id)):
            logger.warning("Некорректный YouTube id: %s", track_id)
            return None, 0

        cached = self._cached_info(track_id)
        if cached:
            picked = self._pick_stream_url(cached, prefer_video=False)
            if picked:
                return picked, self._duration_ms_from_info(cached)

        url = f"https://www.youtube.com/watch?v={track_id}"
        last_exc: BaseException | None = None
        started = monotonic()
        for opts in self._attempt_opts(video=False):
            try:
                with YoutubeDL(opts) as yt:
                    info = yt.extract_info(url, download=False)
                self._store_info(track_id, info)
                picked = self._pick_stream_url(info, prefer_video=False)
                if picked:
                    logger.info(
                        "YouTube stream %s in %.2fs via format=%s clients=%s",
                        track_id,
                        monotonic() - started,
                        opts.get("format"),
                        (opts.get("extractor_args") or {})
                        .get("youtube", {})
                        .get("player_client"),
                    )
                    return picked, self._duration_ms_from_info(info)
            except Exception as exc:
                last_exc = exc
                logger.debug(
                    "YouTube stream attempt failed (%s): %s",
                    opts.get("format"),
                    track_id,
                    exc_info=True,
                )
        if last_exc is not None:
            logger.error(
                "Не удалось получить URL потока YouTube: %s",
                track_id,
                exc_info=last_exc,
            )
        else:
            logger.warning("YouTube: нет playable formats для %s", track_id)
        return None, 0

    def sync_video_stream(
        self, track_id: str, height: int = WALLPAPER_DEFAULT_QUALITY
    ) -> tuple[str | None, int]:
        from yt_dlp import YoutubeDL

        from quantis.services.url_resolver import is_youtube_video_id

        if not is_youtube_video_id(str(track_id)):
            logger.warning("Некорректный YouTube id: %s", track_id)
            return None, 0

        cached = self._cached_info(track_id)
        if cached:
            picked = self._pick_stream_url(
                cached, prefer_video=True, target_height=height
            )
            if picked:
                return picked, int(cached.get("duration") or 0)

        url = f"https://www.youtube.com/watch?v={track_id}"
        for opts in self._attempt_opts(video=True, height=height):
            try:
                with YoutubeDL(opts) as yt:
                    info = yt.extract_info(url, download=False)
                self._store_info(track_id, info)
                picked = self._pick_stream_url(
                    info, prefer_video=True, target_height=height
                )
                duration = int((info or {}).get("duration") or 0)
                if picked:
                    return picked, duration
            except Exception:
                logger.debug(
                    "YouTube video attempt failed: %s", track_id, exc_info=True
                )
        logger.error("Не удалось получить URL видео YouTube: %s", track_id)
        return None, 0
