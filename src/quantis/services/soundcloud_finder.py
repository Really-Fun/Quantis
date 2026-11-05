"""Поиск треков SoundCloud через yt-dlp (scsearch)."""

from __future__ import annotations

import logging
from asyncio import get_running_loop
from concurrent.futures import ThreadPoolExecutor

from quantis.models import Track
from quantis.services.soundcloud import (
    track_from_api,
    track_from_ydl,
    watch_url,
    ydl_opts,
)

logger = logging.getLogger(__name__)


class AsyncSoundCloudFinder:
    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        return await get_running_loop().run_in_executor(
            self._executor, self._sync_get_tracks, title, value
        )

    async def get_track(self, track_id: str | int) -> Track | None:
        return await get_running_loop().run_in_executor(
            self._executor, self._sync_get_track, str(track_id)
        )

    async def get_track_from_url(self, url: str) -> Track | None:
        return await get_running_loop().run_in_executor(
            self._executor, self._sync_extract, url
        )

    def _sync_get_tracks(self, title: str, value: int = 5) -> list[Track]:
        limit = max(1, value)
        try:
            return self._search_api(title, limit)
        except Exception:
            logger.debug("SoundCloud api-v2 не ответил — scsearch", exc_info=True)
        return self._search_ydl(title, limit)

    @staticmethod
    def _search_api(title: str, limit: int) -> list[Track]:
        """Один запрос к api-v2 вместо scsearch.

        scsearch yt-dlp на каждый найденный трек делает ещё запрос — 13–21
        запрос, 3–19 с. client_id (и его обновление при 401/403) — те же,
        что у yt-dlp: берём их у его экстрактора.
        """
        from yt_dlp import YoutubeDL

        with YoutubeDL(ydl_opts()) as ydl:
            ie = ydl.get_info_extractor("Soundcloud")
            ie.initialize()  # client_id из кэша yt-dlp или со страницы сайта
            data = ie._call_api(
                ie._API_V2_BASE + "search/tracks",
                title,
                "Searching",
                query={"q": title, "limit": limit * 2},  # часть отсеет DRM
                headers=ie._HEADERS,
            )
        collection = data.get("collection") if isinstance(data, dict) else None
        if not isinstance(collection, list):
            raise RuntimeError("SoundCloud: неожиданный ответ поиска")
        tracks: list[Track] = [
            t for t in map(track_from_api, collection) if t is not None
        ]
        return tracks[:limit]

    def _search_ydl(self, title: str, limit: int) -> list[Track]:
        from yt_dlp import YoutubeDL

        query = f"scsearch{limit}:{title}"
        opts = ydl_opts(extract_flat=True, skip_download=True, noplaylist=False)
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
        except Exception:
            logger.exception("Ошибка поиска SoundCloud: %s", title)
            return []

        entries = (info or {}).get("entries") or []
        tracks: list[Track] = []
        for entry in entries:
            if not entry:
                continue
            track = track_from_ydl(entry)
            if track is not None:
                tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    def _sync_get_track(self, track_id: str) -> Track | None:
        return self._sync_extract(watch_url(track_id))

    def _sync_extract(self, url: str) -> Track | None:
        from yt_dlp import YoutubeDL

        opts = ydl_opts(extract_flat=False)
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            return track_from_ydl(info)
        except Exception:
            logger.exception("Не удалось получить трек SoundCloud: %s", url)
            return None
