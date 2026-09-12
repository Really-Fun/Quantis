"""Сохранение истории прослушивания по событиям плеера."""

from __future__ import annotations

from time import monotonic

from PySide6.QtCore import QObject, QTimer

from quantis.core.async_bridge import AsyncBridge
from quantis.database.sync_history import listen_delta_ms
from quantis.models import Track
from quantis.player import Player
from quantis.plugins.event_bus import EventBus
from quantis.services.track_history import TrackHistoryService


class PlaybackHistoryWatcher(QObject):
    """Пишет прогресс и недавние треки в БД при воспроизведении."""

    def __init__(
        self,
        player: Player,
        history: TrackHistoryService,
        event_bus: EventBus,
        bridge: AsyncBridge,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._history = history
        self._bridge = bridge
        self._event_bus = event_bus
        self._current: Track | None = None
        self._last_pos = 0
        self._last_dur = 0
        self._wall_mono = 0.0

        self._eco = False
        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._on_tick)

        event_bus.track_changed.connect(self._on_track_changed)
        player.on_track_finished(self._on_finished)
        player.on_playback_paused(self._on_pause)
        player.on_playback_resumed(self._on_resume)

    def set_eco(self, enabled: bool) -> None:
        self._eco = enabled
        self._timer.setInterval(20_000 if enabled else 5000)

    def _interval_cap_ms(self) -> int:
        return max(self._timer.interval() + 2_500, 8_000)

    def _resolved_duration(self, track: Track | None) -> int:
        duration = max(0, int(self._player.duration))
        if duration <= 0:
            duration = self._last_dur if track is self._current else 0
        if track is not None and duration > 0:
            catalog = max(0, int(getattr(track, "duration_ms", 0) or 0))
            if catalog <= 0:
                track.duration_ms = duration
        return duration

    def _capture(self) -> tuple[int, int]:
        pos = max(0, int(self._player.time))
        dur = self._resolved_duration(self._current)
        if dur > 0:
            self._last_dur = dur
        return pos, self._last_dur

    def _arm_wall(self) -> None:
        self._wall_mono = monotonic() if self._player.is_playing() else 0.0

    def _consume_wall_ms(self) -> int:
        started = self._wall_mono
        if started <= 0:
            self._arm_wall()
            return 0
        now = monotonic()
        raw = int((now - started) * 1000)
        self._wall_mono = now if self._player.is_playing() else 0.0
        cap = self._interval_cap_ms()
        duration = self._last_dur or self._resolved_duration(self._current)
        if duration > 0:
            cap = min(cap, duration)
        return max(0, min(raw, cap))

    def _listen_delta(self, position_ms: int, wall_ms: int) -> int:
        return listen_delta_ms(
            wall_ms=wall_ms,
            position_ms=position_ms,
            last_position_ms=self._last_pos,
            duration_ms=self._last_dur,
            interval_cap_ms=self._interval_cap_ms(),
        )

    def _commit_position(self, position_ms: int) -> None:
        if position_ms > 0:
            self._last_pos = position_ms

    def _on_track_changed(self, track: Track) -> None:
        previous = self._current
        leftover = self._consume_wall_ms()
        if previous is not None and previous is not track:
            self._save(
                previous,
                force=True,
                position_ms=self._last_pos,
                duration_ms=self._last_dur or self._resolved_duration(previous),
                wall_ms=leftover,
            )
        self._current = track
        self._last_pos = 0
        self._last_dur = max(0, int(getattr(track, "duration_ms", 0) or 0))
        self._arm_wall()
        self._timer.start()
        self._save(track, force=True, wall_ms=0)

    def _on_tick(self) -> None:
        if self._current is None:
            return
        wall = self._consume_wall_ms() if self._player.is_playing() else 0
        self._save(self._current, wall_ms=wall)

    def _on_pause(self) -> None:
        if self._current is None:
            return
        wall = self._consume_wall_ms()
        self._save(self._current, force=True, wall_ms=wall)

    def _on_resume(self) -> None:
        self._arm_wall()

    def _on_finished(self) -> None:
        track = self._current
        if track is None:
            return
        position_ms, duration_ms = self._capture()
        wall = self._consume_wall_ms()
        if duration_ms > 0:
            position_ms = max(position_ms, duration_ms)
        delta = self._listen_delta(position_ms, wall)
        self._commit_position(position_ms)

        async def job() -> None:
            await self._history.mark_track_finished(
                track,
                position_ms,
                duration_ms,
                played_delta_ms=delta,
            )
            self._bridge.invoke_main(self._event_bus.history_updated.emit)

        self._bridge.schedule(job())

    def _save(
        self,
        track: Track,
        *,
        force: bool = False,
        position_ms: int | None = None,
        duration_ms: int | None = None,
        wall_ms: int = 0,
    ) -> None:
        if position_ms is None or duration_ms is None:
            cap_pos, cap_dur = self._capture()
            if position_ms is None:
                position_ms = cap_pos
            if duration_ms is None:
                duration_ms = cap_dur
        delta = self._listen_delta(position_ms, wall_ms)
        self._commit_position(position_ms)
        force = force or delta > 0

        async def job() -> None:
            await self._history.save_progress(
                track,
                position_ms,
                duration_ms,
                force=force,
                played_delta_ms=delta,
            )
            if force:
                self._bridge.invoke_main(self._event_bus.history_updated.emit)

        self._bridge.schedule(job())
