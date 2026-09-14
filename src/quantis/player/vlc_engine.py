"""Движок воспроизведения на libVLC (python-vlc)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QTimer, Signal

from quantis.player.volume import output_percent

logger = logging.getLogger(__name__)


def _find_vlc_plugin_path() -> str | None:
    import os
    import sys

    env = os.environ.get("VLC_PLUGIN_PATH") or os.environ.get("VLC_HOME")
    if env:
        plugins = Path(env)
        if (plugins / "plugins").is_dir():
            return str(plugins / "plugins")
        if plugins.name == "plugins" and plugins.is_dir():
            return str(plugins)

    # Рядом с exe (сборки Quantis-VLC)
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
        for candidate in (base / "plugins", base / "vlc" / "plugins"):
            if candidate.is_dir():
                return str(candidate)

    if sys.platform == "win32":
        pf = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        pf86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        for root in (pf / "VideoLAN" / "VLC", pf86 / "VideoLAN" / "VLC"):
            plugins = root / "plugins"
            if plugins.is_dir():
                return str(plugins)
    return None


class _VlcBridge(QObject):
    """Маршалинг событий libVLC в главный поток Qt."""

    playing = Signal()
    paused = Signal()
    stopped = Signal()
    ended = Signal()
    errored = Signal(str)


class VlcMediaEngine:
    """Аудио через libVLC. Требует установленный VLC или bundled plugins."""

    def __init__(self) -> None:
        import vlc

        plugin_path = _find_vlc_plugin_path()
        args = ["--no-video", "--quiet", "--intf", "dummy", "--no-video-title-show"]
        if plugin_path:
            args.extend([f"--plugin-path={plugin_path}"])
            logger.info("VLC plugins: %s", plugin_path)

        self._vlc = vlc
        self._instance = vlc.Instance(*args)
        if self._instance is None:
            raise RuntimeError(
                "Не удалось создать VLC Instance. Установите VLC или укажите VLC_HOME."
            )
        self._player = self._instance.media_player_new()
        self._bridge = _VlcBridge()
        self._volume = 80
        self._duck_gain = 1.0
        self._apply_output_volume()

        self._playing_cbs: list[Callable[[], None]] = []
        self._paused_cbs: list[Callable[[], None]] = []
        self._stopped_cbs: list[Callable[[], None]] = []
        self._ended_cbs: list[Callable[[], None]] = []
        self._error_cbs: list[Callable[[str], None]] = []
        self._pending_seek_ms = 0
        self._last_time_ms = 0
        self._buffering = False

        self._bridge.playing.connect(lambda: self._fire(self._playing_cbs))
        self._bridge.paused.connect(lambda: self._fire(self._paused_cbs))
        self._bridge.stopped.connect(lambda: self._fire(self._stopped_cbs))
        self._bridge.ended.connect(lambda: self._fire(self._ended_cbs))
        self._bridge.errored.connect(lambda msg: self._fire_error(msg))

        em = self._player.event_manager()
        em.event_attach(vlc.EventType.MediaPlayerPlaying, self._on_vlc_playing)
        em.event_attach(vlc.EventType.MediaPlayerPaused, self._on_vlc_paused)
        em.event_attach(vlc.EventType.MediaPlayerStopped, self._on_vlc_stopped)
        em.event_attach(vlc.EventType.MediaPlayerEndReached, self._on_vlc_ended)
        em.event_attach(vlc.EventType.MediaPlayerEncounteredError, self._on_vlc_error)
        try:
            em.event_attach(vlc.EventType.MediaPlayerBuffering, self._on_vlc_buffering)
        except (AttributeError, TypeError, ValueError):
            logger.debug("VLC buffering events unavailable")

    @staticmethod
    def _fire(callbacks: list[Callable[[], None]]) -> None:
        for callback in callbacks:
            callback()

    def _fire_error(self, message: str) -> None:
        for callback in self._error_cbs:
            callback(message)

    def _emit(self, signal) -> None:
        # libVLC вызывает из своего потока — в Qt через queued signal.
        QTimer.singleShot(0, signal.emit)

    def _on_vlc_playing(self, _event) -> None:
        self._emit(self._bridge.playing)
        QTimer.singleShot(0, self._apply_pending_seek)

    def _on_vlc_paused(self, _event) -> None:
        self._emit(self._bridge.paused)

    def _on_vlc_stopped(self, _event) -> None:
        self._emit(self._bridge.stopped)

    def _on_vlc_ended(self, _event) -> None:
        # libVLC из EndReached нельзя трогать; stop() обязателен, иначе
        # следующий play() нового URL молча не стартует.
        QTimer.singleShot(0, self._finish_ended)

    def _finish_ended(self) -> None:
        try:
            self._player.stop()
        except Exception:
            logger.debug("VLC stop after EndReached failed", exc_info=True)
        self._fire(self._ended_cbs)

    def _on_vlc_error(self, _event) -> None:
        QTimer.singleShot(0, lambda: self._bridge.errored.emit("VLC playback error"))

    def _on_vlc_buffering(self, event) -> None:
        try:
            cache = float(event.u.new_cache)
        except Exception:
            cache = 100.0
        self._buffering = cache < 100.0

    def play_media(self, source: str) -> None:
        self._pending_seek_ms = 0
        self._last_time_ms = 0
        self._buffering = True
        # После EndReached без stop() новый media не играет.
        try:
            self._player.stop()
        except Exception:
            logger.debug("VLC stop before play failed", exc_info=True)
        path = source
        if not source.startswith(("http://", "https://", "file:")):
            path = str(Path(source).resolve())
        media = self._instance.media_new(path)
        self._player.set_media(media)
        self._apply_output_volume()
        if self._player.play() == -1:
            self._bridge.errored.emit(f"VLC не смог открыть: {source}")

    def set_video_sink(self, sink) -> None:
        _ = sink

    def pause_media(self) -> None:
        self._player.set_pause(1)

    def resume_media(self) -> None:
        self._player.set_pause(0)
        self._schedule_pending_seek()

    def stop_media(self) -> None:
        self._pending_seek_ms = 0
        self._player.stop()

    def is_playing(self) -> bool:
        return bool(self._player.is_playing())

    def is_buffering(self) -> bool:
        return self._buffering

    def get_position_ms(self) -> int:
        value = self._player.get_time()
        if value is not None and value > 0:
            self._last_time_ms = int(value)
            return self._last_time_ms
        return self._last_time_ms

    def set_position_ms(self, ms: int) -> None:
        self._player.set_time(max(0, int(ms)))

    def request_seek(self, ms: int) -> None:
        self._pending_seek_ms = max(0, int(ms))
        self._schedule_pending_seek()

    def _schedule_pending_seek(self) -> None:
        QTimer.singleShot(0, self._apply_pending_seek)
        QTimer.singleShot(250, self._apply_pending_seek)
        QTimer.singleShot(800, self._apply_pending_seek)

    def _apply_pending_seek(self) -> None:
        ms = self._pending_seek_ms
        if ms <= 0:
            return
        duration = self.get_duration_ms()
        target = ms
        if duration > 400:
            target = min(ms, duration - 400)
        self._player.set_time(target)
        position = self.get_position_ms()
        if duration > 0 and abs(position - target) <= 2000:
            self._pending_seek_ms = 0

    def get_duration_ms(self) -> int:
        value = self._player.get_length()
        return max(0, int(value)) if value is not None and value >= 0 else 0

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
        self._player.audio_set_volume(output_percent(self._volume, self._duck_gain))

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
