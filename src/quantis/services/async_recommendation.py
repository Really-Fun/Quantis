"""Асинхронный сервис рекомендаций треков (YouTube Radio / Watch Playlist)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Iterable

from quantis.config import Clients
from quantis.models import RecommendationPlaylist, Track, YoutubeTrack
from quantis.models.track import clock_to_ms, seconds_to_ms
from quantis.services.async_finder import (
    AsyncYoutubeFinder,
    youtube_author_from_payload,
)
from quantis.services.url_resolver import is_youtube_video_id

logger = logging.getLogger(__name__)

BATCH_SIZE = 5
PLAYLIST_NAME = "Рекомендации"
_WATCH_FETCH_LIMIT = 18
_FALLBACK_QUERY = "recommended mix"


class AsyncRecommendation:
    """Радио из истории: пачки по 5 треков с YouTube, с догрузкой в конце."""

    def __init__(
        self,
        youtube_finder: AsyncYoutubeFinder,
        client: Any | None = None,
    ) -> None:
        self._finder = youtube_finder
        self._client = client
        self._extend_lock: asyncio.Lock | None = None

    @property
    def _yt(self):
        if self._client is None:
            self._client = Clients().get_youtube_client()
        return self._client

    def _lock(self) -> asyncio.Lock:
        if self._extend_lock is None:
            self._extend_lock = asyncio.Lock()
        return self._extend_lock

    async def generate_from_history(
        self,
        history_tracks: Iterable[Track],
        *,
        limit: int = BATCH_SIZE,
    ) -> RecommendationPlaylist:
        """Первая пачка: сид из БД (недавние), треки — с YouTube."""
        seeds = tuple(history_tracks)
        playlist = RecommendationPlaylist(
            name=PLAYLIST_NAME,
            tracks=(),
            seeds=seeds,
            infinite=True,
        )
        seed = playlist.take_seed(seeds[0]) if seeds else None
        tracks = await self._related_tracks(
            seed,
            limit=limit,
            exclude_ids=_exclude_ids(seed),
        )
        if not tracks:
            tracks = await self._search_fallback(
                limit,
                query=_query_for(seed),
                exclude_ids=_exclude_ids(seed),
            )
        playlist.append_tracks(tracks[:limit])
        return playlist

    async def generate_radio_from_track(
        self, track: Track, *, limit: int = BATCH_SIZE
    ) -> RecommendationPlaylist:
        tracks = await self._related_tracks(
            track,
            limit=limit,
            exclude_ids={str(track.track_id)},
        )
        playlist = RecommendationPlaylist(
            name=PLAYLIST_NAME,
            tracks=tracks[:limit],
            seeds=(track,),
            infinite=True,
        )
        playlist._seed_index = 1
        return playlist

    async def continue_after_finish(
        self,
        playlist: RecommendationPlaylist,
        finished: Track,
    ) -> Track | None:
        """Если очередь кончилась — ещё 5 с YouTube, затем следующий трек."""
        await self.ensure_extended(playlist, finished)
        return self._linear_next(playlist)

    async def ensure_extended(
        self,
        playlist: RecommendationPlaylist,
        seed: Track,
        *,
        limit: int = BATCH_SIZE,
    ) -> int:
        """Догружает пачку, если нет следующего трека. Сколько добавили."""
        async with self._lock():
            if playlist.tracks._index + 1 < len(playlist):
                return 0
            existing = {str(t.track_id) for t in playlist.tracks.values}
            collected: list[Track] = []
            attempts = 0
            max_attempts = max(3, len(playlist.seeds) or 1)
            current_seed = seed
            while len(collected) < limit and attempts < max_attempts:
                more = await self._related_tracks(
                    current_seed,
                    limit=limit,
                    exclude_ids=existing,
                )
                for track in more:
                    vid = str(track.track_id)
                    if vid in existing:
                        continue
                    collected.append(track)
                    existing.add(vid)
                    if len(collected) >= limit:
                        break
                if len(collected) >= limit:
                    break
                current_seed = playlist.take_seed(seed)
                attempts += 1
            if len(collected) < limit:
                extra = await self._search_fallback(
                    limit - len(collected),
                    query=_query_for(seed),
                    exclude_ids=existing,
                )
                collected.extend(extra)
            added = playlist.append_tracks(collected[:limit])
            if added:
                logger.info("Рекомендации: подгружено ещё %s треков", added)
            else:
                logger.info("Рекомендации: не удалось получить следующую пачку")
            return added

    async def _related_tracks(
        self,
        seed: Track | None,
        *,
        limit: int,
        exclude_ids: set[str],
    ) -> list[Track]:
        if seed is None:
            return []
        try:
            video_id = seed.track_id if isinstance(seed, YoutubeTrack) else None
            if not video_id or not is_youtube_video_id(str(video_id)):
                video_id = await self._get_youtube_id(seed)
            if not video_id:
                return []
            exclude = set(exclude_ids)
            exclude.add(str(video_id))
            exclude.add(str(seed.track_id))
            result = await asyncio.get_running_loop().run_in_executor(
                self._finder.executor,
                lambda: self._yt.get_watch_playlist(
                    videoId=str(video_id),
                    limit=_WATCH_FETCH_LIMIT,
                ),
            )
            return self._tracks_from_watch(
                result,
                limit=limit,
                exclude_ids=exclude,
            )
        except Exception:
            logger.exception("Рекомендации: не удалось получить related для «%s»", seed)
            return []

    def _tracks_from_watch(
        self,
        result: dict | None,
        *,
        limit: int,
        exclude_ids: set[str],
    ) -> list[Track]:
        tracks: list[Track] = []
        for track_info in (result or {}).get("tracks") or []:
            if not isinstance(track_info, dict):
                continue
            video_id = str(track_info.get("videoId") or "")
            if not is_youtube_video_id(video_id) or video_id in exclude_ids:
                continue
            tracks.append(
                YoutubeTrack(
                    track_id=video_id,
                    title=str(track_info.get("title") or "").strip() or video_id,
                    author=youtube_author_from_payload(track_info),
                    downloaded=False,
                    duration_ms=seconds_to_ms(track_info.get("lengthSeconds"))
                    or clock_to_ms(track_info.get("duration")),
                )
            )
            exclude_ids.add(video_id)
            if len(tracks) >= limit:
                break
        return tracks

    async def _search_fallback(
        self,
        limit: int,
        *,
        query: str,
        exclude_ids: set[str],
    ) -> list[Track]:
        try:
            found = await self._finder.get_tracks(query, value=max(limit * 2, limit))
        except Exception:
            logger.exception("Рекомендации: fallback-поиск не удался")
            return []
        tracks: list[Track] = []
        for track in found:
            vid = str(track.track_id)
            if vid in exclude_ids:
                continue
            tracks.append(track)
            exclude_ids.add(vid)
            if len(tracks) >= limit:
                break
        return tracks

    async def _get_youtube_id(self, track: Track) -> str | None:
        """Ищет YouTube ID для не-YouTube трека."""
        try:
            results = await self._finder.get_tracks(
                f"{track.title} {track.author}", value=1
            )
        except Exception:
            logger.debug("Рекомендации: поиск YouTube ID", exc_info=True)
            return None
        if not results:
            return None
        return str(results[0].track_id)

    @staticmethod
    def _linear_next(playlist: RecommendationPlaylist) -> Track | None:
        idx = playlist.tracks._index
        if idx + 1 >= len(playlist):
            return None
        playlist.set_current_track(idx + 1)
        return playlist.get_current_track()


def _exclude_ids(seed: Track | None) -> set[str]:
    if seed is None:
        return set()
    return {str(seed.track_id)}


def _query_for(seed: Track | None) -> str:
    if seed is None:
        return _FALLBACK_QUERY
    query = f"{seed.title} {seed.author}".strip()
    return query or _FALLBACK_QUERY


# Алиас для обратной совместимости
AsyncRecomendation = AsyncRecommendation
