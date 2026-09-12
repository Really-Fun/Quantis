"""Движок воспроизведения на Qt Multimedia (FFmpeg)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QPlaybackOptions

logger = logging.getLogger(__name__)


class QtMediaEngine:
    """Владеет QMediaPlayer и QAudioOutput; события — через колбэки."""

    def __init__(self) -> None:
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._player.setAudioOutput(self._audio)
        self._apply_playback_options()

        self._playing_cbs: list[Callable[[], None]] = []
        self._paused_cbs: list[Callable[[], None]] = []
        self._stopped_cbs: list[Callable[[], None]] = []
        self._ended_cbs: list[Callable[[], None]] = []
        self._error_cbs: list[Callable[[str], None]] = []

        self._pending_seek_ms = 0
        self._volume = int(round(self._audio.volume() * 100))
        self._duck_gain = 1.0
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.playbackStateChanged.connect(self._on_playback_state)
        self._player.errorOccurred.connect(self._on_error)
        self._player.durationChanged.connect(self._on_duration_changed)

    @property
    def media_player(self) -> QMediaPlayer:
        """Совместимость со старым кодом/тестами."""
        return self._player

    @property
    def audio_output(self) -> QAudioOutput:
        return self._audio

    @staticmethod
    def _to_url(source: str) -> QUrl:
        if source.startswith(("http://", "https://")):
            return QUrl(source)
        return QUrl.fromLocalFile(str(Path(source).resolve()))

    @staticmethod
    def _apply_playback_options_to(player: QMediaPlayer) -> None:
        options = QPlaybackOptions()
        options.setPlaybackIntent(QPlaybackOptions.PlaybackIntent.Playback)
        # Пока прокси переподключается к CDN, localhost-сокет Qt не должен отвалиться.
        options.setNetworkTimeout(60_000)
        player.setPlaybackOptions(options)

    def _apply_playback_options(self) -> None:
        try:
            self._apply_playback_options_to(self._player)
        except Exception:
            logger.debug("QPlaybackOptions недоступны", exc_info=True)

    def play_media(self, source: str) -> None:
        self._pending_seek_ms = 0
        self._player.setSource(self._to_url(source))
        self._player.play()

    def pause_media(self) -> None:
        self._player.pause()

    def resume_media(self) -> None:
        self._player.play()
        self._apply_pending_seek()

    def stop_media(self) -> None:
        self._pending_seek_ms = 0
        self._player.stop()

    def is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def is_buffering(self) -> bool:
        status = self._player.mediaStatus()
        return status in (
            QMediaPlayer.MediaStatus.LoadingMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
            QMediaPlayer.MediaStatus.StalledMedia,
        )

    def get_position_ms(self) -> int:
        return max(0, int(self._player.position()))

    def set_position_ms(self, ms: int) -> None:
        self._player.setPosition(max(0, int(ms)))

    def request_seek(self, ms: int) -> None:
        self._pending_seek_ms = max(0, int(ms))
        self._apply_pending_seek()

    def _apply_pending_seek(self) -> None:
        ms = self._pending_seek_ms
        if ms <= 0:
            return
        duration = self.get_duration_ms()
        status = self._player.mediaStatus()
        ready = status in (
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferingMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        )
        if duration <= 0 and not ready:
            return
        target = ms
        if duration > 400:
            target = min(ms, duration - 400)
        self._player.setPosition(target)
        position = self.get_position_ms()
        if duration > 0 and abs(position - target) <= 1500:
            self._pending_seek_ms = 0

    def _on_duration_changed(self, _duration: int) -> None:
        self._apply_pending_seek()

    def get_duration_ms(self) -> int:
        return max(0, int(self._player.duration()))

    def get_volume(self) -> int:
        return self._volume

    def set_volume(self, value: int) -> None:
        self._volume = max(0, min(100, int(value)))
        self._apply_output_volume()

    def get_duck_gain(self) -> float:
        return self._duck_gain

    def set_duck_gain(self, gain: float) -> None:
        self._duck_gain = max(0.0, min(1.0, float(gain)))
        self._apply_output_volume()

    def _apply_output_volume(self) -> None:
        self._audio.setVolume((self._volume / 100.0) * self._duck_gain)

    def on_playing(self, callback: Callable[[], None]) -> None:
        self._playing_cbs.append(callback)

    def on_paused(self, callback: Callable[[], None]) -> None:
        self._paused_cbs.append(callback)

    def on_stopped(self, callback: Callable[[], None]) -> None:
        self._stopped_cbs.append(callback)

    def on_ended(self, callback: Callable[[], None]) -> None:
        self._ended_cbs.append(callback)

    def on_error(self, callback: Callable[[str], None]) -> None:
        self._error_cbs.append(callback)

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        self._apply_pending_seek()
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        duration = self.get_duration_ms()
        position = self.get_position_ms()
        if duration > 1000 and position < duration - 1000:
            logger.warning(
                "Поток оборвался рано (%sms из %sms)",
                position,
                duration,
            )
        for callback in self._ended_cbs:
            callback()

    def _on_playback_state(self, state: QMediaPlayer.PlaybackState) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            for callback in self._playing_cbs:
                callback()
        elif state == QMediaPlayer.PlaybackState.PausedState:
            for callback in self._paused_cbs:
                callback()
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            for callback in self._stopped_cbs:
                callback()

    def _on_error(self, error: QMediaPlayer.Error, message: str) -> None:
        if error == QMediaPlayer.Error.NoError:
            return
        text = message or str(error)
        for callback in self._error_cbs:
            callback(text)
