"""Контроллер воспроизведения.

Управляет play / pause / volume / track loading.
Не занимается визуализацией — за это отвечает VizualPlayer.

Паттерн: Singleton
Single Responsibility: только воспроизведение.
Dependency Inversion: зависит от VLCEngine, а не создаёт VLC-объекты напрямую.
"""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QTimer, Signal
from vlc import EventType

from models import Track
from providers import PathProvider
from services import AsyncStreamer, TrackHistoryService
from player.engine import VLCEngine


class Player(QObject):
    """Синглтон-плеер. Только воспроизведение."""

    track_finished = Signal()
    track_changed = Signal(object)  # emitted with Track when a new track starts
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
        self._history_service = TrackHistoryService()

        self.current_track: Track | None = None
        self.on_pause: bool = False

        self.events = self._engine.playback_player.event_manager()
        self.events.event_attach(EventType.MediaPlayerEndReached, self._on_end)

        self._persist_timer = QTimer(self)
        self._persist_timer.setInterval(5000)
        self._persist_timer.timeout.connect(self._persist_current_progress)
        self._persist_timer.start()

        self._initialized = True

    # --- Playback API ---

    async def play_track(self, track: Track) -> None:
        """Загружает и проигрывает трек (локальный или стрим)."""
        if self.current_track is not None and self.current_track != track:
            self._save_progress_background(self.current_track, force=True)

        self.on_pause = False
        self.current_track = track

        source = await self._resolve_source(track)
        if source is None:
            return

        self._engine.play_both(source)
        # Сразу создаем/обновляем запись в истории, чтобы трек появлялся
        # в "Недавно прослушанных" уже во время прослушивания.
        self._save_progress_background(track, force=True)
        self._start_resume_restore(track)
        self.track_changed.emit(track)

    def pause(self) -> None:
        self.on_pause = True
        self._engine.pause_both()
        if self.current_track is not None:
            self._save_progress_background(self.current_track, force=True)

    def resume(self) -> None:
        self.on_pause = False
        self._engine.resume_both()

    def is_playing(self) -> bool:
        return self._engine.playback_player.is_playing()
    
    def _on_end(self, _event=None) -> None:
        """Обрабатывает завершение трека от VLC и эмитит сигнал окончания."""
        if self.current_track is not None:
            duration = max(0, self.duration)
            self._run_background(
                self._history_service.mark_track_finished(
                    self.current_track,
                    position_ms=duration,
                    duration_ms=duration,
                )
            )
        self.track_finished.emit()

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

    def _persist_current_progress(self) -> None:
        """Периодически сохраняет прогресс текущего трека."""
        if self.current_track is None:
            return
        if self.is_playing():
            self._save_progress_background(self.current_track, force=False)

    def _save_progress_background(self, track: Track, *, force: bool) -> None:
        """Сохраняет прогресс в фоне без блокировки UI."""
        position = max(0, self.time)
        duration = max(0, self.duration)
        self._run_background(
            self._history_service.save_progress(
                track,
                position_ms=position,
                duration_ms=duration,
                force=force,
            )
        )

    def _start_resume_restore(self, track: Track) -> None:
        """Запускает восстановление позиции воспроизведения в фоне."""
        self._run_background(self._restore_track_position(track))

    async def _restore_track_position(self, track: Track) -> None:
        """Восстанавливает позицию для трека после запуска playback."""
        await asyncio.sleep(0.35)
        if self.current_track != track:
            return
        resume_pos = await self._history_service.get_resume_position(track)
        if resume_pos > 0:
            self.time = resume_pos

    @staticmethod
    def _run_background(coro) -> None:
        """Безопасно создает фоновую asyncio-задачу."""
        try:
            asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            pass
