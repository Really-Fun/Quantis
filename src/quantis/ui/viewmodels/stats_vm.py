from __future__ import annotations

import asyncio
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from quantis.controllers.playback_controller import PlaybackController
from quantis.core.async_bridge import AsyncBridge
from quantis.database.sync_history import ListeningSummary
from quantis.models import Track
from quantis.models.playlist import RecommendationPlaylist
from quantis.services.track_history import TrackHistoryService
from quantis.ui.models import TrackListModel
from quantis.ui.viewmodels.base_viewmodel import BaseViewModel

_LIST_LIMIT = 8


@dataclass(frozen=True)
class StatsSnapshot:
    summary: ListeningSummary
    most: tuple[Track, ...]
    least: tuple[Track, ...]


class StatsViewModel(BaseViewModel):
    stats_changed = Signal()

    def __init__(
        self,
        history: TrackHistoryService,
        playback: PlaybackController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._history = history
        self._playback = playback
        self._bridge: AsyncBridge | None = None
        self._most_model = TrackListModel()
        self._least_model = TrackListModel()
        self._snapshot = StatsSnapshot(
            summary=ListeningSummary(),
            most=(),
            least=(),
        )

    @property
    def most_model(self) -> TrackListModel:
        return self._most_model

    @property
    def least_model(self) -> TrackListModel:
        return self._least_model

    @property
    def snapshot(self) -> StatsSnapshot:
        return self._snapshot

    def request_load(self, bridge: AsyncBridge) -> None:
        self._bridge = bridge
        from quantis.ui.async_ui import schedule

        schedule(self._load_async(), bridge)

    async def _load_async(self) -> None:
        bridge = self._bridge
        if bridge is None:
            return
        summary = await self._history.get_listening_summary()
        most, least = await asyncio.gather(
            self._history.get_ranked_tracks(_LIST_LIMIT, descending=True),
            self._history.get_ranked_tracks(_LIST_LIMIT, descending=False),
        )
        snapshot = StatsSnapshot(
            summary=summary,
            most=tuple(most),
            least=tuple(least),
        )

        def apply() -> None:
            self._snapshot = snapshot
            self._most_model.set_tracks(list(most))
            self._least_model.set_tracks(list(least))
            self.stats_changed.emit()

        bridge.invoke_main(apply)

    async def play_most_at(self, index: int) -> None:
        await self._play_from_model(self._most_model, index, "Топ прослушиваний")

    async def play_least_at(self, index: int) -> None:
        await self._play_from_model(self._least_model, index, "Редкие треки")

    async def _play_from_model(
        self, model: TrackListModel, index: int, name: str
    ) -> None:
        track = model.get_track(index)
        if track is None:
            return
        tracks = model.all_tracks()
        playlist = RecommendationPlaylist(name=name, tracks=tracks)
        playlist.set_current_track(index)
        self._playback.playlist_manager.set_playlist(playlist)
        await self._playback.play_track(track)

    def set_playing_track(self, track: Track | None) -> None:
        self._most_model.set_playing_track(track)
        self._least_model.set_playing_track(track)
