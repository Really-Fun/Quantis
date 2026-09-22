"""Сервис пользовательских плейлистов (JSON в playlists/)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from quantis.models import Track, UserPlaylist
from quantis.providers.path_provider import PathProvider
from quantis.utils import playlist_helper as helper


class UserPlaylistsService:
    """CRUD поверх ``playlist_helper``."""

    _instance: UserPlaylistsService | None = None

    def __new__(cls) -> UserPlaylistsService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        PathProvider.ensure_storage_dirs()

    @property
    def playlists_dir(self) -> str:
        return PathProvider.playlists_folder().rstrip("/\\")

    async def list_names(self) -> list[str]:
        return await asyncio.to_thread(
            helper.list_user_playlist_names, self.playlists_dir
        )

    async def create(self, name: str) -> Path:
        return await asyncio.to_thread(
            helper.create_user_playlist_file, name, self.playlists_dir
        )

    async def add_track(self, playlist_name: str, track: Track) -> bool:
        """True если трек добавлен, False если уже был в плейлисте."""
        return await asyncio.to_thread(
            helper.add_track_to_user_playlist,
            playlist_name,
            track.track_id,
            track.title,
            track.author,
            self.playlists_dir,
            str(track.source),
        )

    async def remove_track(self, playlist_name: str, track: Track) -> bool:
        return await asyncio.to_thread(
            helper.remove_track_from_user_playlist,
            playlist_name,
            track.track_id,
            self.playlists_dir,
        )

    async def delete(self, name: str) -> None:
        await asyncio.to_thread(
            helper.delete_user_playlist_file, name, self.playlists_dir
        )

    async def rename(self, old_name: str, new_name: str) -> Path:
        return await asyncio.to_thread(
            helper.rename_user_playlist_file,
            old_name,
            new_name,
            self.playlists_dir,
        )

    async def load_all(self, *, include_empty: bool = True) -> list[UserPlaylist]:
        return await asyncio.to_thread(self._load_all_sync, include_empty)

    def _load_all_sync(self, include_empty: bool) -> list[UserPlaylist]:
        playlists_dir = Path(self.playlists_dir)
        playlists_dir.mkdir(parents=True, exist_ok=True)
        result: list[UserPlaylist] = []
        json_files = sorted(
            playlists_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        provider = PathProvider()
        for path in json_files:
            try:
                playlist = UserPlaylist.get_playlist_from_path(str(path))
            except Exception:
                continue
            if playlist is None:
                continue
            if not include_empty and not playlist.tracks.values:
                continue
            if not playlist.cover_path and playlist.tracks.values:
                first = playlist.tracks.values[0]
                playlist.cover_path = provider.get_cover_path(first)
            result.append(playlist)
        return result
