"""Сервис истории прослушивания."""

from __future__ import annotations

import asyncio
from time import monotonic

from quantis.database import sync_history
from quantis.database.sync_history import ListeningSummary
from quantis.models import RecentlyPlayedPlaylist, Track
from quantis.providers import TrackManager
from quantis.services.track_builder import (
    build_track_key,
    build_tracks_from_entries,
    split_track_key,
)


class TrackHistoryService:
    """Сервис сохранения/чтения прогресса треков (singleton)."""

    _instance: TrackHistoryService | None = None

    def __new__(cls) -> TrackHistoryService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, save_interval_sec: float = 5.0) -> None:
        if getattr(self, "_initialized", False):
            return
        self._save_interval_sec = max(1.0, save_interval_sec)
        self._last_saved_by_key: dict[str, float] = {}
        self._track_manager = TrackManager()
        self._initialized = True

    @staticmethod
    def build_track_key(track: Track) -> str:
        return build_track_key(track)

    @staticmethod
    def _split_track_key(track_key: str, source_fallback: str) -> tuple[str, str]:
        return split_track_key(track_key, source_fallback)

    async def get_resume_position(self, track: Track) -> int:
        track_key = self.build_track_key(track)
        return await asyncio.to_thread(sync_history.get_saved_position, track_key)

    async def save_progress(
        self,
        track: Track,
        position_ms: int,
        duration_ms: int,
        *,
        force: bool = False,
        played_delta_ms: int | None = None,
    ) -> None:
        del position_ms  # таймкод не пишем — старт всегда с нуля
        track_key = self.build_track_key(track)
        now = monotonic()
        last_saved = self._last_saved_by_key.get(track_key, 0.0)
        if not force and now - last_saved < self._save_interval_sec:
            return

        await asyncio.to_thread(
            sync_history.upsert_progress,
            track_key=track_key,
            title=track.title,
            author=track.author,
            source=str(track.source),
            position_ms=0,
            duration_ms=duration_ms,
            listen_increment=0,
            played_delta_ms=played_delta_ms,
        )
        self._last_saved_by_key[track_key] = now

    async def mark_track_finished(
        self,
        track: Track,
        position_ms: int,
        duration_ms: int,
        *,
        played_delta_ms: int | None = None,
    ) -> None:
        del position_ms  # таймкод не пишем — старт всегда с нуля
        track_key = self.build_track_key(track)
        await asyncio.to_thread(
            sync_history.upsert_progress,
            track_key=track_key,
            title=track.title,
            author=track.author,
            source=str(track.source),
            position_ms=0,
            duration_ms=duration_ms,
            listen_increment=1,
            played_delta_ms=played_delta_ms,
        )
        self._last_saved_by_key[track_key] = monotonic()

    async def get_recent_playlist(
        self, limit: int = 24
    ) -> RecentlyPlayedPlaylist | None:
        entries = await asyncio.to_thread(sync_history.fetch_recent_entries, limit)
        if not entries:
            return None
        tracks = await asyncio.to_thread(
            build_tracks_from_entries,
            entries,
            self._track_manager,
            include_listen_count=True,
        )
        return RecentlyPlayedPlaylist(tracks=tracks)

    async def get_listening_summary(self) -> ListeningSummary:
        return await asyncio.to_thread(sync_history.fetch_listening_summary)

    async def get_ranked_tracks(
        self,
        limit: int = 10,
        *,
        descending: bool = True,
        min_listens: int = 1,
    ) -> list[Track]:
        entries = await asyncio.to_thread(
            sync_history.fetch_ranked_entries,
            limit,
            descending=descending,
            min_listens=min_listens,
        )
        if not entries:
            return []
        return await asyncio.to_thread(
            build_tracks_from_entries,
            entries,
            self._track_manager,
            include_listen_count=True,
        )

    async def close(self) -> None:
        """Заглушка для совместимости при завершении приложения."""
