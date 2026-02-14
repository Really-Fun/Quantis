"""Общий VLC-движок.

Владеет VLC Instance и двумя MediaPlayer:
  - playback_player  — воспроизведение звука (обычный вывод)
  - analysis_player  — захват PCM через callbacks (без вывода звука)

Паттерн: Singleton
Single Responsibility: жизненный цикл VLC-объектов + синхронизация медии.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from vlc import Instance, MediaPlayer, Media

# Задержка запуска analysis_player (мс).
_ANALYSIS_DELAY_MS = 1500


class VLCEngine:
    """Синглтон VLC-движка с двумя плеерами."""

    _instance: VLCEngine | None = None

    def __new__(cls) -> VLCEngine:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return

        self._vlc_instance: Instance = Instance()

        self._playback_player: MediaPlayer = self._vlc_instance.media_player_new()
        self._analysis_player: MediaPlayer = self._vlc_instance.media_player_new()

        self._analysis_timer = QTimer()
        self._analysis_timer.setSingleShot(True)
        self._analysis_timer.timeout.connect(self._start_analysis)

        self._initialized = True


    @property
    def instance(self) -> Instance:
        return self._vlc_instance

    @property
    def playback_player(self) -> MediaPlayer:
        return self._playback_player

    @property
    def analysis_player(self) -> MediaPlayer:
        return self._analysis_player

    def load_media(self, source: str) -> Media:
        """Создаёт Media из пути или URL.
        
        Args:
            source (str): Путь к медиа-файлу или URL.

        Returns:
            Media: Объект Media.
        """
        return self._vlc_instance.media_new(source)

    def play_both(self, source: str) -> None:
        """Запускает playback сразу, analysis с задержкой для синхронизации.
        
        Args:
            source (str): Путь к медиа-файлу или URL.
        """
        self._analysis_timer.stop()

        media_play = self.load_media(source)
        media_analysis = self.load_media(source)

        self._playback_player.set_media(media_play)
        self._analysis_player.set_media(media_analysis)

        self._playback_player.play()

        self._analysis_timer.start(_ANALYSIS_DELAY_MS)

    def _start_analysis(self) -> None:
        self._analysis_player.play()

    def pause_both(self) -> None:
        self._analysis_timer.stop()
        self._playback_player.pause()
        self._analysis_player.pause()

    def resume_both(self) -> None:
        self._playback_player.play()
        self._analysis_player.play()