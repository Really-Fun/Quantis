from __future__ import annotations

import asyncio
import random

from PySide6.QtCore import QObject, Signal

from quantis.controllers.playback_controller import PlaybackController
from quantis.core.async_bridge import AsyncBridge
from quantis.models import (
    DownloadPlaylist,
    LikedPlaylist,
    RecentlyPlayedPlaylist,
    Track,
    UserPlaylist,
    WavePlaylist,
)
from quantis.models.playlist import Playlist, RecommendationPlaylist
from quantis.ui.cover_prefetch import schedule_cover_prefetch
from quantis.ui.models import TrackListModel
from quantis.ui.viewmodels.base_viewmodel import BaseViewModel


class PlaylistViewModel(BaseViewModel):
    """ViewModel страницы плейлиста с ленивой подгрузкой треков."""

    playlist_changed = Signal()
    covers_ready = Signal()
    tracks_mutated = Signal()
    PLAYLIST_BATCH_SIZE = 80

    def __init__(
        self,
        playback: PlaybackController,
        bridge: AsyncBridge | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._playback = playback
        self._bridge = bridge
        self._playlist: Playlist | None = None
        self._model = TrackListModel(batch_size=self.PLAYLIST_BATCH_SIZE)

    @property
    def model(self) -> TrackListModel:
        return self._model

    @property
    def playlist(self) -> Playlist | None:
        return self._playlist

    @property
    def track_count(self) -> int:
        if self._playlist is None:
            return 0
        return len(self._playlist)

    @property
    def can_remove_tracks(self) -> bool:
        return isinstance(self._playlist, (UserPlaylist, DownloadPlaylist))

    @property
    def remove_action_label(self) -> str:
        if isinstance(self._playlist, DownloadPlaylist):
            return "Удалить скачанный файл"
        return "Убрать из плейлиста"

    def remove_confirm_text(self, track: Track) -> tuple[str, str]:
        playlist = self._playlist
        name = playlist.name if playlist is not None else "плейлиста"
        if isinstance(playlist, DownloadPlaylist):
            return (
                "Удалить файл",
                f"Удалить «{track.title}» с диска? Файл нельзя будет слушать офлайн.",
            )
        return (
            "Убрать из плейлиста",
            f"Убрать «{track.title}» из «{name}»?",
        )

    def set_bridge(self, bridge: AsyncBridge) -> None:
        self._bridge = bridge

    def set_playlist(self, playlist: Playlist) -> None:
        from quantis.ui.views.widgets.cover_art import clear_cover_cache

        self._playlist = playlist
        tracks = list(playlist.tracks.values)
        self._model.set_tracks(tracks)
        clear_cover_cache()
        self.playlist_changed.emit()
        if self._bridge is not None and tracks:
            schedule_cover_prefetch(
                tracks,
                self._playback.music.downloader,
                self._bridge,
                on_done=lambda: self.covers_ready.emit(),
                limit=200,
            )

    def clear(self) -> None:
        """Освобождает треки при уходе со страницы плейлиста."""
        from quantis.ui.views.widgets.cover_art import clear_cover_cache

        self._playlist = None
        self._model.set_tracks([])
        clear_cover_cache()
        self.playlist_changed.emit()

    def set_playing_track(self, track: Track | None) -> None:
        self._model.set_playing_track(track)

    async def play_all(self, start_index: int = 0) -> None:
        playlist = self._playlist
        if playlist is None:
            return
        await self._start_playlist(playlist, start_index=start_index)

    async def play_shuffled(self) -> None:
        playlist = self._playlist
        if playlist is None:
            return
        tracks = list(playlist.tracks.values)
        if not tracks:
            return
        random.shuffle(tracks)
        working = self._clone_playlist(playlist, tracks)
        working.set_current_track(0)
        self._playback.playlist_manager.set_playlist(working)
        await self._playback.play_track(tracks[0])

    async def play_at(self, index: int) -> None:
        playlist = self._playlist
        if playlist is None:
            return
        tracks = list(playlist.tracks.values)
        if not tracks:
            return
        row = max(0, min(index, len(tracks) - 1))
        await self._start_playlist(playlist, start_index=row)

    async def remove_track_at(self, index: int) -> bool:
        playlist = self._playlist
        track = self._model.get_track(index)
        if playlist is None or track is None or not self.can_remove_tracks:
            return False
        try:
            if isinstance(playlist, UserPlaylist):
                from quantis.services.user_playlists import UserPlaylistsService

                await UserPlaylistsService().remove_track(playlist.name, track)
                playlist.delete_track(track)
            elif isinstance(playlist, DownloadPlaylist):
                await asyncio.to_thread(playlist.delete_track, track)
            else:
                return False
        except Exception as exc:
            self.emit_error(str(exc))
            return False
        self._model.remove_track(index)
        self._drop_from_playing_queue(track)
        self.playlist_changed.emit()
        self.tracks_mutated.emit()
        return True

    def _drop_from_playing_queue(self, track: Track) -> None:
        current = self._playback.playlist_manager.current_playlist
        source = self._playlist
        if current is None or source is None or current is source:
            return
        if type(current) is not type(source):
            return
        if getattr(current, "name", None) != getattr(source, "name", None):
            return
        current.tracks.remove(track)

    async def _start_playlist(self, playlist: Playlist, *, start_index: int) -> None:
        tracks = list(playlist.tracks.values)
        if not tracks:
            return
        index = max(0, min(start_index, len(tracks) - 1))
        working = self._clone_playlist(playlist, tracks)
        working.set_current_track(index)
        self._playback.playlist_manager.set_playlist(working)
        await self._playback.play_track(tracks[index])

    @staticmethod
    def _clone_playlist(playlist: Playlist, tracks: list[Track]) -> Playlist:
        if isinstance(playlist, RecentlyPlayedPlaylist):
            return RecentlyPlayedPlaylist(name=playlist.name, tracks=tracks)
        if isinstance(playlist, LikedPlaylist):
            return LikedPlaylist(name=playlist.name, tracks=tracks)
        if isinstance(playlist, DownloadPlaylist):
            return DownloadPlaylist(name=playlist.name, tracks=tracks)
        if isinstance(playlist, UserPlaylist):
            return UserPlaylist(playlist.name, tracks, playlist.cover_path)
        if isinstance(playlist, RecommendationPlaylist):
            return RecommendationPlaylist(playlist.name, tracks, playlist.cover_path)
        if isinstance(playlist, WavePlaylist):
            return WavePlaylist(
                playlist.name,
                tracks,
                playlist.cover_path,
                source=playlist.source,
                station=playlist.station,
                batch_id=playlist.batch_id,
            )
        return RecommendationPlaylist(playlist.name, tracks, playlist.cover_path)
