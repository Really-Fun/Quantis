"""
Асинхронный поиск треков по платформам:
Yandex
Youtube
SoundCloud
"""

from __future__ import annotations

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import yandex_music.exceptions

from quantis.config import Clients
from quantis.config.credentials import yandex_token
from quantis.models import Track, YoutubeTrack
from quantis.models.track import clock_to_ms, seconds_to_ms
from quantis.services.soundcloud_finder import AsyncSoundCloudFinder
from quantis.services.url_resolver import is_youtube_video_id
from quantis.services.yandex_finder import (
    yandex_track_from_api,
    yandex_tracks_from_search,
)

logger = logging.getLogger(__name__)

_TOPIC_SUFFIX = re.compile(r"\s*[-–—]\s*Topic\s*$", re.IGNORECASE)


def _youtube_duration_ms(payload: dict | None) -> int:
    if not payload:
        return 0
    for key in ("duration_seconds", "lengthSeconds", "length_seconds"):
        ms = seconds_to_ms(payload.get(key))
        if ms:
            return ms
    duration = payload.get("duration")
    if isinstance(duration, (int, float)) or (
        isinstance(duration, str) and duration.strip().isdigit()
    ):
        ms = seconds_to_ms(duration)
        if ms:
            return ms
    return clock_to_ms(duration)


def _clean_youtube_artist_name(name: str) -> str:
    cleaned = _TOPIC_SUFFIX.sub("", name).strip()
    return cleaned or name.strip()


def youtube_author_from_payload(payload: dict | None) -> str:
    """Автор из поиска / get_song / yt-dlp.

    У Topic/ATV ``artists`` часто ``None``, а канал — ``Artist - Topic``.
    ``dict.get("artists", [])`` тогда возвращает ``None``, и ``join`` роняет
    весь ``get_track``.
    """
    if not payload:
        return "Unknown Artist"
    names: list[str] = []
    seen: set[str] = set()

    def add(raw: object) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        cleaned = _clean_youtube_artist_name(text)
        key = cleaned.casefold()
        if not cleaned or key in seen:
            return
        seen.add(key)
        names.append(cleaned)

    artists = payload.get("artists")
    if isinstance(artists, list):
        for item in artists:
            if isinstance(item, dict):
                add(item.get("name") or item.get("text"))
            else:
                add(item)
    elif isinstance(artists, str):
        add(artists)

    for key in ("author", "artist", "uploader", "channel", "channelName"):
        add(payload.get(key))

    return " | ".join(names) if names else "Unknown Artist"


class AsyncFinderInterface(ABC):
    @abstractmethod
    async def get_tracks(self, title: str, value: int = 5) -> list[Track]: ...

    @abstractmethod
    async def get_track(self, track_id: str | int) -> Track | None: ...


class AsyncYandexFinder(AsyncFinderInterface):
    def __init__(self, executor: ThreadPoolExecutor | None = None) -> None:
        self._executor = executor

    def _client(self):
        if not yandex_token():
            return None
        return Clients().get_yandex_client()

    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        client = self._client()
        if client is None:
            logger.warning("Yandex: токен не задан в keyring — поиск только YouTube")
            return []
        try:
            search_result = await client.search(title, type_="track")
            return yandex_tracks_from_search(search_result, value)
        except yandex_music.exceptions.NetworkError:
            logger.exception("Ошибка сети при поиске на Yandex: %s", title)
            return []
        except yandex_music.exceptions.TimedOutError:
            logger.warning("Таймаут Yandex при поиске: %s", title)
            return []
        except yandex_music.exceptions.YandexMusicError:
            logger.exception("Ошибка Yandex Music API при поиске: %s", title)
            return []

    async def get_track(self, track_id: str | int) -> Track | None:
        try:
            yandex_id = int(track_id)
        except (ValueError, TypeError):
            return None

        client = self._client()
        if client is None:
            return None
        try:
            track_info = await client.tracks(yandex_id)
            if not track_info:
                return None
            return yandex_track_from_api(track_info[0])
        except yandex_music.exceptions.YandexMusicError:
            logger.exception(
                "Ошибка Yandex Music API при получении трека: %s", track_id
            )
            return None


class AsyncYoutubeFinder(AsyncFinderInterface):
    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._client = None
        self._executor = executor

    @property
    def client(self):
        if self._client is None:
            self._client = Clients().get_youtube_client()
        return self._client

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor

    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_get_tracks, title, value
        )

    async def get_track(self, track_id: str | int) -> Track | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_get_track, track_id
        )

    async def get_track_from_url(self, url: str) -> Track | None:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, self._sync_get_track_from_url, url
        )

    def _sync_get_track_from_url(self, url: str) -> Track | None:
        from quantis.services.url_resolver import parse_track_id, parse_youtube_video_id

        parsed = parse_track_id(url)
        if parsed is not None:
            source, track_id = parsed
            if source == "youtube":
                return self._sync_get_track_from_yt_dlp(url, track_id)
            return None

        video_id = parse_youtube_video_id(url)
        if video_id:
            return self._sync_get_track_from_yt_dlp(url, video_id)
        return None

    def _sync_get_track_from_yt_dlp(self, url: str, video_id: str) -> Track | None:
        from yt_dlp import YoutubeDL

        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        try:
            with YoutubeDL(opts) as yt:
                info = yt.extract_info(url, download=False)
            if not info:
                return self._sync_get_track(video_id)
            resolved_id = str(info.get("id") or video_id)
            if not is_youtube_video_id(resolved_id):
                return self._sync_get_track(video_id)
            title = str(info.get("title") or "").strip() or resolved_id
            return YoutubeTrack(
                track_id=resolved_id,
                title=title,
                author=youtube_author_from_payload(info),
                downloaded=False,
                duration_ms=_youtube_duration_ms(info),
            )
        except Exception as exc:
            logger.debug("yt-dlp не разобрал URL %s: %s", url, exc)
            return self._sync_get_track(video_id)

    def _sync_get_tracks(self, title: str, value: int = 5) -> list[Track]:
        try:
            results = self.client.search(query=title, filter="songs", limit=value)
            if not results:
                results = self.client.search(query=title, limit=value * 3)
                results = [
                    r
                    for r in (results or [])
                    if r.get("resultType") in ("song", "video")
                ][:value]
            if not results:
                results = [self.client.get_song(videoId=title)["videoDetails"]]
        except Exception as e:
            logger.debug("Ошибка поиска YTMusic для '%s': %s", title, e)
            return []

        tracks = []
        for item in results:
            video_id = str(item.get("videoId") or item.get("video_id") or "")
            if not is_youtube_video_id(video_id):
                continue
            track_title = str(item.get("title") or "").strip() or video_id
            tracks.append(
                YoutubeTrack(
                    track_id=video_id,
                    title=track_title,
                    author=youtube_author_from_payload(item),
                    downloaded=False,
                    duration_ms=_youtube_duration_ms(item),
                )
            )
        return tracks

    def _sync_get_track(self, track_id: str | int) -> Track | None:
        requested = str(track_id).strip()
        try:
            results = self.client.get_song(requested)
            if not results:
                return None
            video_details = results.get("videoDetails") or {}
            resolved_id = str(video_details.get("videoId") or requested)
            if not is_youtube_video_id(resolved_id):
                return None
            title = str(video_details.get("title") or "").strip() or resolved_id
            return YoutubeTrack(
                track_id=resolved_id,
                title=title,
                author=youtube_author_from_payload(video_details),
                downloaded=False,
                duration_ms=_youtube_duration_ms(video_details),
            )
        except Exception as e:
            logger.error("Ошибка YTMusic при получении трека %s: %s", track_id, e)
            if is_youtube_video_id(requested):
                return YoutubeTrack(
                    track_id=requested,
                    title=requested,
                    author="Unknown Artist",
                    downloaded=False,
                )
            return None


class AsyncFinder(AsyncFinderInterface):
    _SOURCE_TIMEOUT_SEC = 10.0
    _SOUNDCLOUD_TIMEOUT_SEC = 15.0
    _DEFAULT_PER_SOURCE = 12
    SEARCH_SOURCES = ("yandex", "youtube", "soundcloud")

    def __init__(self, executor: ThreadPoolExecutor | None = None) -> None:
        from quantis.core.worker_pool import get_worker_pool

        self._owns_executor = False
        self._executor = executor or get_worker_pool()
        self._yandex_finder = AsyncYandexFinder(self._executor)
        self._youtube_finder = AsyncYoutubeFinder(self._executor)
        self._soundcloud_finder = AsyncSoundCloudFinder(self._executor)

    @property
    def youtube(self) -> AsyncYoutubeFinder:
        """YouTube-файндер для переиспользования в других сервисах."""
        return self._youtube_finder

    async def _fetch_source(
        self, source: str, title: str, value: int
    ) -> tuple[str, list[Track]]:
        timeout = (
            self._SOUNDCLOUD_TIMEOUT_SEC
            if source == "soundcloud"
            else self._SOURCE_TIMEOUT_SEC
        )
        try:
            if source == "yandex":
                tracks = await asyncio.wait_for(
                    self._yandex_finder.get_tracks(title, value), timeout=timeout
                )
            elif source == "soundcloud":
                tracks = await asyncio.wait_for(
                    self._soundcloud_finder.get_tracks(title, value), timeout=timeout
                )
            else:
                tracks = await asyncio.wait_for(
                    self._youtube_finder.get_tracks(title, value), timeout=timeout
                )
            return source, tracks
        except TimeoutError:
            logger.warning("Таймаут поиска %s: %s", source, title)
            return source, []
        except Exception as exc:
            logger.exception("Ошибка поиска %s", source, exc_info=exc)
            return source, []

    async def search_source(
        self, source: str, title: str, value: int = 5
    ) -> list[Track]:
        """Поиск в одном источнике (yandex|youtube|soundcloud): с таймаутом,
        ошибки и неизвестный источник — пустой список. Для плагинов."""
        if source not in self.SEARCH_SOURCES:
            return []
        _source, tracks = await self._fetch_source(source, title, value)
        return tracks

    async def iter_track_batches(
        self, title: str, value: int | None = None
    ) -> AsyncIterator[tuple[str, list[Track]]]:
        """Отдаёт результаты по мере готовности каждого источника."""
        limit = value if value is not None else self._DEFAULT_PER_SOURCE
        tasks = [
            asyncio.create_task(self._fetch_source(source, title, limit))
            for source in self.SEARCH_SOURCES
        ]
        try:
            for done in asyncio.as_completed(tasks):
                yield await done
        finally:
            pending = [task for task in tasks if not task.done()]
            for task in pending:
                try:
                    task.cancel()
                except RuntimeError:
                    logger.debug(
                        "Пропущена отмена задачи поиска: event loop уже закрыт"
                    )
            if pending:
                try:
                    await asyncio.gather(*pending, return_exceptions=True)
                except RuntimeError:
                    logger.debug(
                        "Пропущено завершение задач поиска: event loop уже закрыт"
                    )

    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        """Ищет треки на Яндексе, YouTube и SoundCloud одновременно."""
        tracks: list[Track] = []
        async for _source, batch in self.iter_track_batches(title, value):
            tracks.extend(batch)
        return tracks

    async def get_track(self, track_id: str | int) -> Track | None:
        """Ищет трек по ID: Yandex — только для числовых ID, иначе YouTube."""
        if isinstance(track_id, int) or (
            isinstance(track_id, str) and track_id.isdigit()
        ):
            yandex_track = await self._yandex_finder.get_track(track_id)
            if yandex_track is not None:
                return yandex_track
        return await self._youtube_finder.get_track(track_id)

    async def resolve_tracks(
        self,
        *,
        url: str | None = None,
        track_id: str | None = None,
        source: str | None = None,
    ) -> list[Track]:
        """Разрешает трек(и) по прямой ссылке или ID из конкретного источника.

        - Если передан url — определяет источник автоматически по домену.
        - Если передан track_id — требуется source (yandex|youtube|soundcloud).
        Возвращает список Track (для альбома/плейлиста может быть > 1).
        """
        from quantis.services.url_resolver import parse_track_id

        if url:
            parsed = parse_track_id(url)
            if parsed is None:
                logger.warning("Не удалось разобрать ссылку: %s", url)
                return []
            src, resolved_id = parsed
            if src == "yandex":
                track = await self._yandex_finder.get_track(resolved_id)
            elif src == "soundcloud":
                track = await self._soundcloud_finder.get_track_from_url(url)
            else:
                track = await self._youtube_finder.get_track_from_url(url)
            return [track] if track is not None else []

        if track_id:
            normalized_source = (source or "").strip().lower()
            if normalized_source == "yandex":
                track = await self._yandex_finder.get_track(track_id)
            elif normalized_source == "youtube":
                track = await self._youtube_finder.get_track(track_id)
            elif normalized_source == "soundcloud":
                track = await self._soundcloud_finder.get_track(track_id)
            else:
                logger.warning(
                    "resolve_tracks: для track_id=%r нужен source "
                    "(yandex|youtube|soundcloud)",
                    track_id,
                )
                return []
            return [track] if track is not None else []

        return []

    def shutdown(self) -> None:
        """Пул потоков общий — не останавливаем здесь."""
        return
