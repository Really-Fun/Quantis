"""Асинхронный стриминг (получение прямых URL для воспроизведения)."""

from __future__ import annotations

import logging
from asyncio import get_running_loop
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from quantis.config.media_backend import resolve_media_backend
from quantis.models import Track, TrackSource
from quantis.services.soundcloud_streamer import AsyncSoundCloudStreamer
from quantis.services.stream_cache import cached_stream_url
from quantis.services.wallpaper_policy import WALLPAPER_DEFAULT_QUALITY
from quantis.services.yandex_streamer import AsyncStreamerInterface, AsyncYandexStreamer
from quantis.services.youtube_streamer import AsyncYoutubeStreamer

logger = logging.getLogger(__name__)

_PROXY_SOURCES = frozenset({TrackSource.YANDEX, TrackSource.SOUNDCLOUD})


def is_hls_url(url: str | None) -> bool:
    """HLS (m3u8) Qt Multimedia обычно не открывает; VLC — да."""
    if not url:
        return False
    lower = url.lower()
    return ".m3u8" in lower or "m3u8" in lower or "/hls" in lower


def should_buffer_stream(
    track: Track,
    *,
    backend: str | None = None,
    url: str | None = None,
) -> bool:
    """Temp-файл отключён: Qt играет URL через локальный HTTP-прокси."""
    _ = (track, backend, url)
    return False


def should_proxy_stream(
    track: Track,
    *,
    backend: str | None = None,
    url: str | None = None,
) -> bool:
    """Qt + Yandex/SoundCloud MP3 — через 127.0.0.1, Range-reconnect к CDN."""
    chosen = backend or resolve_media_backend()
    if chosen == "vlc":
        return False
    if str(track.source).lower() not in _PROXY_SOURCES:
        return False
    return not is_hls_url(url)


class AsyncStreamer(AsyncStreamerInterface):
    """Фасад над Yandex и YouTube стримерами с кэшированием URL."""

    _URL_CACHE_TTL_SEC = 50
    _URL_CACHE_MAX = 64

    def __init__(self, executor: ThreadPoolExecutor | None = None) -> None:
        from quantis.core.worker_pool import get_worker_pool
        from quantis.services.http_stream_proxy import LocalHttpStreamProxy
        from quantis.services.yandex_progressive_buffer import ProgressiveStreamBuffer

        self._owns_executor = False
        self._executor = executor or get_worker_pool()
        self._yandex = AsyncYandexStreamer(self._executor)
        self._youtube = AsyncYoutubeStreamer(self._executor)
        self._soundcloud = AsyncSoundCloudStreamer(self._executor)
        self._stream_buffer = ProgressiveStreamBuffer(self._fetch_fresh_stream_url)
        self._http_proxy = LocalHttpStreamProxy(self._fetch_fresh_stream_url)
        self._buffer_loop: Any = None
        self._cache: OrderedDict[str, tuple[str, float]] = OrderedDict()

    async def _fetch_fresh_stream_url(self, track: Track) -> str | None:
        """Прямой URL без кэша фасада (для progressive buffer / recovery)."""
        source_type = str(track.source).lower()
        if source_type == TrackSource.YOUTUBE:
            return await self._youtube.get_stream_url(track)
        if source_type == TrackSource.YANDEX:
            return await self._yandex.get_stream_url(track)
        if source_type == TrackSource.SOUNDCLOUD:
            return await self._soundcloud.get_stream_url(track)
        return None

    @cached_stream_url
    async def get_stream_url(self, track: Track) -> str | None:
        source_type = str(track.source).lower()
        if source_type == TrackSource.YOUTUBE:
            return await self._youtube.get_stream_url(track)
        if source_type == TrackSource.YANDEX:
            return await self._yandex.get_stream_url(track)
        if source_type == TrackSource.SOUNDCLOUD:
            return await self._soundcloud.get_stream_url(track)
        raise ValueError(f"Неизвестный источник платформы у трека: {track.source!r}")

    async def open_playback(self, track: Track) -> str | None:
        """Прямой URL. Qt Yandex/SoundCloud MP3 — через localhost-прокси."""
        url = await self.get_stream_url(track)
        if not url:
            return None
        if (
            str(track.source).lower() == TrackSource.SOUNDCLOUD
            and is_hls_url(url)
            and resolve_media_backend() != "vlc"
        ):
            logger.warning(
                "SoundCloud HLS «%s» — Qt Multimedia может не открыть поток",
                track.title,
            )
        if should_proxy_stream(track, url=url):
            self._buffer_loop = get_running_loop()
            return await self._http_proxy.mount(track, url)
        return url

    async def prefetch_stream(self, track: Track) -> None:
        try:
            await self.get_stream_url(track)
        except Exception:
            logger.debug("Prefetch stream failed for %s", track.track_id, exc_info=True)

    async def wait_for_more_prefix(self, track: Track) -> bool:
        return await self._stream_buffer.wait_for_more_prefix(track)

    async def seek_to_ms(
        self, track: Track, position_ms: int, *, source: str | None = None
    ) -> bool:
        """Готовит буфер к перемотке: прямые URL и локальные файлы не трогаем."""
        if source is not None and not self._stream_buffer.owns(source):
            return True
        return await self._stream_buffer.seek_to_ms(track, position_ms)

    def report_position_ms(self, track: Track, position_ms: int) -> None:
        self._stream_buffer.report_position_ms(track, position_ms)

    async def get_video_url(
        self,
        track: Track,
        finder: object | None = None,
        *,
        height: int = WALLPAPER_DEFAULT_QUALITY,
        exclude_itags: frozenset[str] | None = None,
    ) -> str | None:
        url, _duration = await self.get_video_info(
            track, finder, height=height, exclude_itags=exclude_itags
        )
        return url

    async def get_video_info(
        self,
        track: Track,
        finder: object | None = None,
        *,
        height: int = WALLPAPER_DEFAULT_QUALITY,
        exclude_itags: frozenset[str] | None = None,
    ) -> tuple[str | None, int]:
        video_id = await self._resolve_youtube_video_id(track, finder)
        if not video_id:
            return None, 0
        return await self._youtube.get_video_info(
            video_id, height=height, exclude_itags=exclude_itags
        )

    async def _resolve_youtube_video_id(
        self, track: Track, finder: object | None
    ) -> str | None:
        source_type = str(track.source).lower()
        if source_type == TrackSource.YOUTUBE:
            return str(track.track_id)
        if finder is None:
            return None
        query = f"{track.title} {track.author}"
        try:
            results = await finder.get_tracks(query, value=3)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("Поиск YouTube-видео для обоев: %s", query)
            return None
        youtube_hit = next(
            (t for t in results if str(t.source).lower() == TrackSource.YOUTUBE),
            None,
        )
        return str(youtube_hit.track_id) if youtube_hit else None

    def invalidate(self, track: Track) -> None:
        key = f"{track.source}:{track.track_id}"
        self._cache.pop(key, None)
        self._stream_buffer.invalidate_track(track)
        self._http_proxy.invalidate_track(track)
        if str(track.source).lower() == TrackSource.YOUTUBE:
            self._youtube.invalidate(str(track.track_id))

    def set_eco(self, enabled: bool) -> None:
        self._stream_buffer.set_eco(enabled)
        if enabled:
            self._youtube.clear_cache()

    def shutdown(self) -> None:
        if self._buffer_loop is not None:
            import asyncio
            from concurrent.futures import TimeoutError as FuturesTimeoutError

            async def _close() -> None:
                await self._stream_buffer.close()
                await self._http_proxy.close()

            loop = self._buffer_loop
            self._buffer_loop = None
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                loop.create_task(_close())
            else:
                future = asyncio.run_coroutine_threadsafe(_close(), loop)
                try:
                    future.result(timeout=3)
                except FuturesTimeoutError:
                    logger.debug("Таймаут остановки stream proxy")
                except Exception:
                    logger.debug("Ошибка остановки stream proxy", exc_info=True)
        if self._owns_executor:
            self._executor.shutdown(wait=False)
