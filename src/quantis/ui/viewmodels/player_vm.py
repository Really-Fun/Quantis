from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from quantis.controllers.playback_controller import PlaybackController
from quantis.models import Track
from quantis.models.repeat_mode import RepeatMode
from quantis.player import Player
from quantis.plugins.event_bus import EventBus
from quantis.ui.preferences import UiPreferences
from quantis.ui.viewmodels.base_viewmodel import BaseViewModel


class PlayerViewModel(BaseViewModel):
    track_changed = Signal(object)
    is_playing_changed = Signal(bool)
    position_changed = Signal(int)
    duration_changed = Signal(int)
    volume_changed = Signal(int)
    repeat_mode_changed = Signal(object)

    def __init__(
        self,
        playback: PlaybackController,
        player: Player,
        event_bus: EventBus,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._playback = playback
        self._player = player
        self._event_bus = event_bus
        self._eco = False
        self._last_duration = -1
        self._stall_last_pos = -1
        self._stall_last_move = 0.0
        self._end_ticks = 0
        self._stall_grace_sec = 8.0
        self._stall_buffering_grace_sec = 18.0
        self._tick = QTimer(self)
        self._tick.setInterval(250)
        self._tick.timeout.connect(self._update_timeline)

        event_bus.track_changed.connect(self._on_track_changed)
        event_bus.playback_paused.connect(self._on_paused)
        event_bus.playback_resumed.connect(self._on_resumed)
        event_bus.track_finished.connect(self._on_track_finished)

    def set_eco(self, enabled: bool) -> None:
        self._eco = enabled
        self._tick.setInterval(2000 if enabled else 250)

    def start_updates(self) -> None:
        if not self._tick.isActive():
            self._tick.start()

    def stop_updates(self) -> None:
        self._tick.stop()

    @property
    def current_track(self) -> Track | None:
        return self._playback.current_track

    def toggle_pause(self) -> None:
        self._playback.toggle_pause()

    def play_next(self) -> None:
        self._event_bus.next_requested.emit()

    def play_previous(self) -> None:
        self._event_bus.previous_requested.emit()

    @property
    def repeat_mode(self) -> RepeatMode:
        return self._playback.repeat_mode

    def cycle_repeat_mode(self) -> None:
        mode = self._playback.cycle_repeat_mode()
        self.repeat_mode_changed.emit(mode)

    def set_volume(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        self._player.volume = clamped
        UiPreferences().set_volume(clamped)
        self.volume_changed.emit(clamped)

    def nudge_volume(self, delta: int) -> None:
        self.set_volume(int(self._player.volume) + int(delta))

    def seek(self, position_ms: int) -> None:
        # Слайдер уводим сразу, а сам плеер — через контроллер: он ещё должен
        # догрузить буфер и подтянуть видео-фон.
        self._stall_last_pos = position_ms
        self._stall_last_move = time.monotonic()
        self._end_ticks = 0
        self._playback.seek(position_ms)
        self.position_changed.emit(position_ms)

    def sync_from_player(self) -> None:
        """Синхронизирует UI с текущим состоянием Qt-плеера."""
        if self._playback.current_track is not None:
            self.track_changed.emit(self._playback.current_track)
        self.is_playing_changed.emit(self._player.is_playing())
        self._publish_duration(max(0, self._player.duration))
        self.position_changed.emit(max(0, self._player.time))
        if self._player.current_source:
            self.start_updates()

    def _update_timeline(self) -> None:
        if not self._player.current_source:
            return
        if not getattr(self._playback, "audio_live", True):
            return
        if getattr(self._playback, "is_seeking", False):
            return
        position = max(0, self._player.time)
        duration = max(0, self._player.duration)
        self.position_changed.emit(position)
        self._publish_duration(duration)
        reported = max(duration, self._last_duration)
        self._playback.notify_progress(position)
        self._check_natural_end(position, reported)
        self._check_playback_stall(position, reported)

    def _check_natural_end(self, position: int, duration: int) -> None:
        if duration < 2000 or self._player.on_pause:
            self._end_ticks = 0
            return
        if position < duration - 400:
            self._end_ticks = 0
            return
        self._end_ticks += 1
        needed = 1 if self._eco else 2
        if self._end_ticks < needed:
            return
        self._end_ticks = 0
        notify = getattr(self._player, "notify_natural_end", None)
        if callable(notify):
            notify()

    def _check_playback_stall(self, position: int, duration: int) -> None:
        now = time.monotonic()
        if abs(position - self._stall_last_pos) >= 750:
            self._stall_last_pos = position
            self._stall_last_move = now
            return
        if self._player.on_pause or not self._player.current_source:
            return
        if duration < 5000 or position < 3000 or position >= duration - 2000:
            return
        buffering = bool(getattr(self._player, "is_buffering", lambda: False)())
        grace = self._stall_buffering_grace_sec if buffering else self._stall_grace_sec
        if now - self._stall_last_move < grace:
            return
        self._stall_last_move = now
        self._playback.request_playback_recovery(position)

    def _publish_duration(self, duration: int) -> None:
        if duration <= 0:
            return
        if duration == self._last_duration:
            return
        # Мелкий откат — шум растущего файла. Крупный — движок поправил враньё.
        if 0 < duration < self._last_duration:
            if duration >= int(self._last_duration * 0.9) - 1000:
                return
        self._last_duration = duration
        self.duration_changed.emit(duration)

    def _on_track_changed(self, track: Track) -> None:
        self._stall_last_pos = -1
        self._stall_last_move = time.monotonic()
        self._last_duration = -1
        self._end_ticks = 0
        self.track_changed.emit(track)
        self.position_changed.emit(0)
        catalog = max(0, int(getattr(track, "duration_ms", 0) or 0))
        self._last_duration = catalog if catalog > 0 else -1
        self.duration_changed.emit(catalog)
        self.start_updates()

    def _on_paused(self) -> None:
        self.is_playing_changed.emit(False)

    def _on_resumed(self) -> None:
        self.is_playing_changed.emit(True)
        self.start_updates()

    def _on_track_finished(self) -> None:
        self.is_playing_changed.emit(False)
        self.stop_updates()
