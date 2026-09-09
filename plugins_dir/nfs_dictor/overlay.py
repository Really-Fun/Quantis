"""Второй QMediaPlayer — только голос диктора."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class VoiceOverlay(QObject):
    """Локальный mp3 поверх основного плеера. Не трогает громкость трека."""

    started = Signal()
    ended = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._audio.setVolume(1.0)
        self._armed = False
        self._player.mediaStatusChanged.connect(self._on_status)
        self._player.errorOccurred.connect(self._on_error)

    def play(self, path: str | Path) -> None:
        self._armed = True
        self._player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
        self._player.play()
        self.started.emit()

    def stop(self) -> None:
        self._armed = False
        self._player.stop()

    def pause(self) -> None:
        if self._armed:
            self._player.pause()

    def resume(self) -> None:
        if self._armed:
            self._player.play()

    def is_active(self) -> bool:
        return self._armed

    def _on_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if not self._armed:
            return
        if status != QMediaPlayer.MediaStatus.EndOfMedia:
            return
        self._armed = False
        self.ended.emit()

    def _on_error(self, error: QMediaPlayer.Error, _message: str) -> None:
        if error == QMediaPlayer.Error.NoError or not self._armed:
            return
        self._armed = False
        self.ended.emit()
