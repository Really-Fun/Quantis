"""Сервис любимых треков."""

from __future__ import annotations

import asyncio

from quantis.database import sync_history
from quantis.models import LikedPlaylist, Track
from quantis.providers import TrackManager
from quantis.services.track_builder import build_track_key, build_tracks_from_entries


class LikedTracksService:
    """CRUD для плейлиста «Любимые»."""

    _instance: LikedTracksService | None = None

    def __new__(cls) -> LikedTracksService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._track_manager = TrackManager()
        self._initialized = True

    async def is_liked(self, track: Track) -> bool:
        key = build_track_key(track)
        return await asyncio.to_thread(sync_history.is_track_liked, key)

    async def set_liked(self, track: Track, liked: bool) -> None:
        await asyncio.to_thread(
            sync_history.set_track_liked,
            track_key=build_track_key(track),
            title=track.title,
            author=track.author,
            source=str(track.source),
            liked=liked,
        )

    async def toggle(self, track: Track) -> bool:
        liked = await self.is_liked(track)
        await self.set_liked(track, not liked)
        return not liked

    async def get_playlist(self) -> LikedPlaylist:
        entries = await asyncio.to_thread(sync_history.fetch_liked_entries)
        tracks = await asyncio.to_thread(self._build_tracks, entries)
        return LikedPlaylist(tracks=tracks)

    def _build_tracks(self, entries: list[dict]) -> list[Track]:
        return build_tracks_from_entries(entries, self._track_manager)
