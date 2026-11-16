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
    order_changed = Signal()
    PLAYLIST_BATCH_SIZE = 80
    SORT_ORDERS = {
        "original",
        "title_asc",
        "title_desc",
        "artist_asc",
        "artist_desc",
        "duration_asc",
        "duration_desc",
        "shuffled",
    }

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
        self._sort_order = "original"
        self._original_tracks: list[Track] = []

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
    def sort_order(self) -> str:
        return self._sort_order

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

        previous = self._playlist
        same_playlist = (
            previous is not None
            and type(previous) is type(playlist)
            and previous.name == playlist.name
        )
        order = self._sort_order if same_playlist else "original"
        visible = list(self._model.all_tracks()) if same_playlist else []
        self._playlist = playlist
        tracks = list(playlist.tracks.values)
        self._sort_order = order
        self._original_tracks = list(tracks)
        if order == "shuffled":
            by_id = {(str(t.source), str(t.track_id)): t for t in tracks}
            kept = [
                by_id[key]
                for old in visible
                if (key := (str(old.source), str(old.track_id))) in by_id
            ]
            kept_ids = {(str(t.source), str(t.track_id)) for t in kept}
            tracks = kept + [
                t for t in tracks if (str(t.source), str(t.track_id)) not in kept_ids
            ]
        elif order != "original":
            tracks = self._sort_tracks(tracks, order)
        self._model.set_tracks(tracks)
        self.order_changed.emit()
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
        self._sort_order = "original"
        self._original_tracks = []
        self._model.set_tracks([])
        self.order_changed.emit()
        clear_cover_cache()
        self.playlist_changed.emit()

    def set_playing_track(self, track: Track | None) -> None:
        self._model.set_playing_track(track)

    def set_sort_order(self, order: str) -> None:
        if order not in self.SORT_ORDERS:
            raise ValueError(f"Unknown playlist sort order: {order}")
        playlist = self._playlist
        if playlist is None:
            return
        if order == "shuffled":
            tracks = list(self._model.all_tracks())
            random.shuffle(tracks)
            if len(tracks) > 1 and tracks == self._model.all_tracks():
                tracks = tracks[1:] + tracks[:1]
        else:
            tracks = self._sort_tracks(list(self._original_tracks), order)
        self._sort_order = order
        self._model.set_tracks(tracks)
        self.order_changed.emit()

    @staticmethod
    def _sort_tracks(tracks: list[Track], order: str) -> list[Track]:
        if order == "original":
            return tracks
        field, direction = order.split("_", 1)
        if field == "duration":
            # Unknown duration stays at the bottom in both directions.
            return sorted(
                tracks,
                key=lambda track: (
                    track.duration_ms <= 0,
                    -track.duration_ms if direction == "desc" else track.duration_ms,
                ),
            )
        key = (
            (lambda track: track.title)
            if field == "title"
            else (lambda track: track.author)
        )
        return sorted(
            tracks,
            key=lambda track: key(track).casefold().replace("ё", "е"),
            reverse=direction == "desc",
        )

    def sync_appended(self) -> None:
        """Подтянуть новые треки, если очередь выросла."""
        playlist = self._playlist
        if playlist is None:
            return
        known = self._model.all_tracks()
        fresh = list(playlist.tracks.values)
        known_ids = {(str(t.source), str(t.track_id)) for t in known}
        added = [t for t in fresh if (str(t.source), str(t.track_id)) not in known_ids]
        if not added:
            return
        self._original_tracks.extend(added)
        if self._sort_order in ("original", "shuffled"):
            self._model.append_tracks(added)
        else:
            self._model.set_tracks(
                self._sort_tracks(list(self._original_tracks), self._sort_order)
            )
        self.playlist_changed.emit()
        self.tracks_mutated.emit()

    async def play_all(self, start_index: int = 0) -> None:
        playlist = self._playlist
        if playlist is None:
            return
        await self._start_playlist(playlist, start_index=start_index)

    async def play_shuffled(self) -> None:
        playlist = self._playlist
        if playlist is None:
            return
        self.set_sort_order("shuffled")
        await self._start_playlist(playlist, start_index=0)

    async def play_at(self, index: int) -> None:
        playlist = self._playlist
        if playlist is None:
            return
        tracks = self._model.all_tracks()
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
        self._original_tracks = [
            item for item in self._original_tracks if item != track
        ]
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
        tracks = list(self._model.all_tracks())
        if not tracks:
            return
        index = max(0, min(start_index, len(tracks) - 1))
        infinite = isinstance(playlist, RecommendationPlaylist) and playlist.infinite
        if infinite and tuple(tracks) == playlist.tracks.values:
            working = playlist
        else:
            working = self._clone_playlist(playlist, tracks)
        if infinite and working is not playlist:
            self._playlist = working
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
            clone = RecommendationPlaylist(
                playlist.name,
                tracks,
                playlist.cover_path,
                seeds=playlist.seeds,
                infinite=playlist.infinite,
            )
            clone._seed_index = playlist._seed_index
            return clone
        if isinstance(playlist, WavePlaylist):
            return WavePlaylist(
                playlist.name,
                tracks,
                playlist.cover_path,
                source=playlist.source,
                seeds=playlist.seeds,
                session_id=playlist.session_id,
                batch_id=playlist.batch_id,
            )
        return RecommendationPlaylist(playlist.name, tracks, playlist.cover_path)
