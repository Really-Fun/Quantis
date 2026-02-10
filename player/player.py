"""Контроллер воспроизведения.

Управляет play / pause / volume / track loading.
Не занимается визуализацией — за это отвечает VizualPlayer.

Паттерн: Singleton
Single Responsibility: только воспроизведение.
Dependency Inversion: зависит от VLCEngine, а не создаёт VLC-объекты напрямую.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from qasync import asyncSlot

from models import Track
from providers import PathProvider
from services import AsyncStreamer
from player.engine import VLCEngine


class Player(QObject):
    """Синглтон-плеер. Только воспроизведение."""

    track_finished = Signal()
    _instance: Player | None = None

    def __new__(cls, *args, **kwargs) -> Player:
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()

        self._engine = VLCEngine()
        self._path_provider = PathProvider()
        self._streamer = AsyncStreamer()

        self.current_track: Track | None = None
        self.on_pause: bool = False

        self._initialized = True

    # --- Playback API ---

    async def play_track(self, track: Track) -> None:
        """Загружает и проигрывает трек (локальный или стрим)."""
        self.on_pause = False
        self.current_track = track

        source = await self._resolve_source(track)
        if source is None:
            return

        self._engine.play_both(source)

    def pause(self) -> None:
        self.on_pause = True
        self._engine.pause_both()

    def resume(self) -> None:
        self.on_pause = False
        self._engine.resume_both()

    def is_playing(self) -> bool:
        return self._engine.playback_player.is_playing()

    @property
    def volume(self) -> int:
        return self._engine.playback_player.audio_get_volume()

    @volume.setter
    def volume(self, value: int) -> None:
        self._engine.playback_player.audio_set_volume(value)

    @property
    def time(self) -> int:
        """Текущая позиция воспроизведения в мс."""
        return self._engine.playback_player.get_time()

    @time.setter
    def time(self, time_in_ms: int) -> None:
        self._engine.playback_player.set_time(time_in_ms)
        self._engine.analysis_player.set_time(time_in_ms)

    @property
    def duration(self) -> int:
        """Длительность текущего трека в мс."""
        return self._engine.playback_player.get_length()

    # --- Internal ---

    async def _resolve_source(self, track: Track) -> str | None:
        """Возвращает путь к файлу или URL стрима."""
        if track.downloaded:
            try:
                return self._path_provider.get_track_path(track)
            except FileNotFoundError:
                return None
        return await self._streamer.get_stream_url(track)
