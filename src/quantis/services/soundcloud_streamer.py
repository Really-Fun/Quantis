"""SoundCloud streaming via yt-dlp: progressive HTTP MP3, иначе HLS."""

from __future__ import annotations

import logging
from asyncio import get_running_loop
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from quantis.models import Track
from quantis.services.soundcloud import watch_url, ydl_opts
from quantis.services.yandex_streamer import AsyncStreamerInterface

logger = logging.getLogger(__name__)

_AUDIO_FORMAT = (
    "http_mp3_128/bestaudio[format_id!*=preview][ext=mp3]/"
    "bestaudio[format_id!*=preview]/bestaudio"
)


class AsyncSoundCloudStreamer(AsyncStreamerInterface):
    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def get_stream_url(self, track: Track) -> str | None:
        return await get_running_loop().run_in_executor(
            self._executor, self.sync_stream, str(track.track_id)
        )

    def sync_stream(self, track_id: str) -> str | None:
        from yt_dlp import YoutubeDL

        url = watch_url(track_id)
        last_exc: BaseException | None = None
        for opts in (
            ydl_opts(format=_AUDIO_FORMAT, extract_flat=False),
            ydl_opts(extract_flat=False),
        ):
            try:
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                picked = self._pick_stream_url(info)
                if picked:
                    return picked
            except Exception as exc:
                last_exc = exc
                logger.debug(
                    "SoundCloud stream attempt failed: %s", track_id, exc_info=True
                )
        if last_exc is not None:
            logger.error(
                "Не удалось получить URL потока SoundCloud: %s",
                track_id,
                exc_info=last_exc,
            )
        else:
            logger.warning("SoundCloud: нет playable formats для %s", track_id)
        return None

    @staticmethod
    def _is_preview(fmt: dict[str, Any]) -> bool:
        fid = str(fmt.get("format_id") or "").lower()
        url = str(fmt.get("url") or "").lower()
        return "preview" in fid or "/preview/" in url

    @staticmethod
    def _is_playable_format(fmt: dict[str, Any]) -> bool:
        if not fmt.get("url"):
            return False
        ext = str(fmt.get("ext") or "").lower()
        if ext in ("mhtml", "jpg", "png", "webp", "html"):
            return False
        protocol = str(fmt.get("protocol") or "").lower()
        if protocol.startswith("mhtml") or protocol == "mhtml":
            return False
        if protocol and not (
            protocol.startswith("http")
            or "m3u8" in protocol
            or protocol in ("https", "http")
        ):
            return False
        return True

    @classmethod
    def _pick_stream_url(cls, info: dict[str, Any] | None) -> str | None:
        if not info:
            return None

        formats = [f for f in (info.get("formats") or []) if cls._is_playable_format(f)]
        full = [f for f in formats if not cls._is_preview(f)]
        candidates = full or formats

        top_url = info.get("url")
        top_fmt = {
            "url": top_url,
            "protocol": info.get("protocol"),
            "ext": info.get("ext"),
            "format_id": info.get("format_id"),
            "acodec": info.get("acodec"),
            "vcodec": info.get("vcodec"),
        }
        if (
            top_url
            and cls._is_playable_format(top_fmt)
            and not cls._is_preview(top_fmt)
        ):
            protocol = str(info.get("protocol") or "").lower()
            if "m3u8" not in protocol:
                return str(top_url)

        if not candidates:
            return str(top_url) if top_url else None

        def score(fmt: dict[str, Any]) -> tuple:
            protocol = str(fmt.get("protocol") or "").lower()
            ext = str(fmt.get("ext") or "").lower()
            abr = int(fmt.get("abr") or fmt.get("tbr") or 0)
            preview = cls._is_preview(fmt)
            progressive = "m3u8" not in protocol and "hls" not in protocol
            return (
                0 if preview else 1,
                1 if progressive else 0,
                2 if ext == "mp3" else (1 if ext in ("m4a", "aac", "opus") else 0),
                abr,
            )

        best = max(candidates, key=score)
        if cls._is_preview(best):
            logger.warning("SoundCloud отдал только preview (~30с): %s", info.get("id"))
        return str(best.get("url") or "") or None
