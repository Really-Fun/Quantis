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
    wallpaper_format_quality,
    wallpaper_url_itag,
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
    "width",
    "height",
)
_SLIM_INFO_KEYS = (
    "url",
    "protocol",
    "ext",
    "format_id",
    "vcodec",
    "acodec",
    "width",
    "height",
)


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
        self._video_cache: dict[str, tuple[float, dict[str, Any]]] = {}

    def invalidate(self, track_id: str) -> None:
        with self._info_lock:
            key = str(track_id)
            self._info_cache.pop(key, None)
            self._video_cache.pop(key, None)

    def clear_cache(self) -> None:
        with self._info_lock:
            self._info_cache.clear()
            self._video_cache.clear()

    def _cached_info(self, track_id: str) -> dict[str, Any] | None:
        return self._cached_from(self._info_cache, track_id)

    def _cached_video_info(self, track_id: str) -> dict[str, Any] | None:
        return self._cached_from(self._video_cache, track_id)

    def _cached_from(
        self, cache: dict[str, tuple[float, dict[str, Any]]], track_id: str
    ) -> dict[str, Any] | None:
        key = str(track_id)
        now = monotonic()
        with self._info_lock:
            hit = cache.get(key)
            if hit is None:
                return None
            stamped, info = hit
            if now - stamped > _INFO_CACHE_TTL_SEC:
                cache.pop(key, None)
                return None
            return info

    def _store_info(self, track_id: str, info: dict[str, Any] | None) -> None:
        self._store_into(self._info_cache, track_id, info)

    def _store_video_info(self, track_id: str, info: dict[str, Any] | None) -> None:
        self._store_into(self._video_cache, track_id, info)

    def _store_into(
        self,
        cache: dict[str, tuple[float, dict[str, Any]]],
        track_id: str,
        info: dict[str, Any] | None,
    ) -> None:
        slim = slim_youtube_info(info)
        if not slim:
            return
        key = str(track_id)
        with self._info_lock:
            cache[key] = (monotonic(), slim)
            while len(cache) > _INFO_CACHE_MAX:
                oldest = min(cache, key=lambda item: cache[item][0])
                cache.pop(oldest, None)

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
        android_fmt = wallpaper_yt_dlp_android_format(height) if video else fmt

        def build(
            clients: list[str],
            *,
            format_id: str,
            cookies: bool = False,
            skip_player: bool = True,
        ) -> dict:
            youtube: dict[str, Any] = {
                "player_client": clients,
                # Video-only itag 134/160 сидят в adaptive; skip dash их выкидывает,
                # и фон остаётся с тем же itag=18, что и звук.
                "skip": (
                    ["hls", "translated_subs"]
                    if video
                    else ["hls", "dash", "translated_subs"]
                ),
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

        attempts: list[dict] = []
        if video:
            # android больше не отдаёт adaptive 720/1080 — только muxed itag 18.
            attempts.append(build(["tv_embedded"], format_id=fmt, skip_player=False))
        else:
            attempts.append(build(["android"], format_id=android_fmt))
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
        if video:
            attempts.append(
                build(["android"], format_id=android_fmt, skip_player=False)
            )

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

    @classmethod
    def _format_itag(cls, fmt: dict) -> str | None:
        fid = str(fmt.get("format_id") or "").split("-", 1)[0].split("+", 1)[0]
        if fid.isdigit():
            return fid
        return wallpaper_url_itag(str(fmt.get("url") or ""))

    @staticmethod
    def _has_video(fmt: dict) -> bool:
        vcodec = str(fmt.get("vcodec") or "none").lower()
        if vcodec not in ("", "none"):
            return True
        return int(fmt.get("height") or 0) > 0

    @staticmethod
    def _has_audio(fmt: dict) -> bool:
        acodec = str(fmt.get("acodec") or "none").lower()
        return acodec not in ("", "none")

    @classmethod
    def _qt_video_rank(cls, fmt: dict) -> int:
        """Qt Multimedia надёжнее берёт H264/mp4, чем VP9/AV1."""
        vcodec = str(fmt.get("vcodec") or "").lower()
        ext = str(fmt.get("ext") or "").lower()
        if "avc" in vcodec or vcodec.startswith("avc1") or ext == "mp4":
            if "vp" in vcodec or "av01" in vcodec or "av1" in vcodec:
                return 1
            return 2
        if "vp9" in vcodec or "vp09" in vcodec or ext == "webm":
            return 1
        return 0

    @staticmethod
    def _video_height_fit(height: int, target: int) -> int:
        """Ближе к запрошенному качеству лучше; выше цели штрафуем."""
        if height <= 0 or target <= 0:
            return -10_000
        if height <= target:
            return height
        return (2 * target) - height

    @classmethod
    def _format_quality_height(cls, fmt: dict) -> int:
        return wallpaper_format_quality(
            itag=cls._format_itag(fmt),
            width=int(fmt.get("width") or 0),
            height=int(fmt.get("height") or 0),
        )

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
        video_only: bool = False,
        exclude_itags: frozenset[str] | None = None,
    ) -> str | None:
        if not info:
            return None

        blocked = exclude_itags or frozenset()
        formats = [
            fmt
            for fmt in (info.get("formats") or [])
            if cls._is_playable_format(fmt)
            and (not blocked or cls._format_itag(fmt) not in blocked)
        ]
        top_url = info.get("url")
        top_fmt = {
            "url": top_url,
            "protocol": info.get("protocol"),
            "ext": info.get("ext"),
            "format_id": info.get("format_id"),
            "vcodec": info.get("vcodec"),
            "acodec": info.get("acodec"),
            "height": info.get("height"),
            "width": info.get("width"),
        }
        top_blocked = bool(blocked and cls._format_itag(top_fmt) in blocked)
        if top_url and cls._is_playable_format(top_fmt) and not top_blocked:
            if prefer_video:
                if cls._has_video(top_fmt) and (
                    not video_only or not cls._has_audio(top_fmt)
                ):
                    if all(
                        str(fmt.get("url") or "") != str(top_url) for fmt in formats
                    ):
                        formats.append(top_fmt)
            elif cls._has_audio(top_fmt) and not cls._has_video(top_fmt):
                return str(top_url)

        if prefer_video:
            formats = [fmt for fmt in formats if cls._has_video(fmt)]
            if video_only:
                formats = [
                    fmt
                    for fmt in formats
                    if cls._has_video(fmt) and not cls._has_audio(fmt)
                ]
            if not formats:
                if (
                    top_url
                    and not top_blocked
                    and cls._is_playable_format(top_fmt)
                    and cls._has_video(top_fmt)
                    and (not video_only or not cls._has_audio(top_fmt))
                ):
                    return str(top_url)
                return None

        if not formats:
            if top_blocked:
                return None
            return str(top_url) if top_url else None

        def score(fmt: dict) -> tuple:
            has_audio = cls._has_audio(fmt)
            has_video = cls._has_video(fmt)
            audio_only = has_audio and not has_video
            progressive = has_audio and has_video
            ext = str(fmt.get("ext") or "").lower()
            abr = int(fmt.get("abr") or fmt.get("tbr") or 0)
            if prefer_video:
                only_video = has_video and not has_audio
                return (
                    2 if only_video else 1,
                    cls._video_height_fit(
                        cls._format_quality_height(fmt), target_height
                    ),
                    cls._qt_video_rank(fmt),
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
        self,
        video_id: str,
        height: int = WALLPAPER_DEFAULT_QUALITY,
        exclude_itags: frozenset[str] | None = None,
    ) -> tuple[str | None, int]:
        return await get_running_loop().run_in_executor(
            self._executor,
            self.sync_video_stream,
            video_id,
            height,
            exclude_itags,
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
        self,
        track_id: str,
        height: int = WALLPAPER_DEFAULT_QUALITY,
        exclude_itags: frozenset[str] | None = None,
    ) -> tuple[str | None, int]:
        from yt_dlp import YoutubeDL

        from quantis.services.url_resolver import is_youtube_video_id

        if not is_youtube_video_id(str(track_id)):
            logger.warning("Некорректный YouTube id: %s", track_id)
            return None, 0

        blocked = exclude_itags or frozenset()
        height = clamp_wallpaper_quality(height)

        def pick(info: dict[str, Any] | None, *, video_only: bool) -> str | None:
            return self._pick_stream_url(
                info,
                prefer_video=True,
                target_height=height,
                video_only=video_only,
                exclude_itags=blocked,
            )

        def duration_of(info: dict[str, Any] | None) -> int:
            return int((info or {}).get("duration") or 0)

        for cached in (self._cached_video_info(track_id), self._cached_info(track_id)):
            picked = pick(cached, video_only=True)
            if picked:
                return picked, duration_of(cached)

        url = f"https://www.youtube.com/watch?v={track_id}"
        muxed_fallback: str | None = None
        muxed_duration = 0
        for opts in self._attempt_opts(video=True, height=height):
            try:
                with YoutubeDL(opts) as yt:
                    info = yt.extract_info(url, download=False)
                self._store_video_info(track_id, info)
                picked = pick(info, video_only=True)
                duration = duration_of(info)
                if picked:
                    logger.info(
                        "YouTube video %s: video-only via format=%s clients=%s",
                        track_id,
                        opts.get("format"),
                        (opts.get("extractor_args") or {})
                        .get("youtube", {})
                        .get("player_client"),
                    )
                    return picked, duration
                if muxed_fallback is None:
                    muxed = pick(info, video_only=False)
                    if muxed:
                        muxed_fallback = muxed
                        muxed_duration = duration
            except Exception:
                logger.debug(
                    "YouTube video attempt failed: %s", track_id, exc_info=True
                )
        if muxed_fallback:
            logger.info(
                "YouTube video %s: только muxed, video-only нет",
                track_id,
            )
            return muxed_fallback, muxed_duration
        logger.error("Не удалось получить URL видео YouTube: %s", track_id)
        return None, 0
