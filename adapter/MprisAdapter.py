"""Адаптер MPRIS для интеграции медиаплеера в Linux."""

import os
from decimal import Decimal
from typing import Callable, Optional

from PySide6.QtCore import QTimer

from mpris_server.adapters import MprisAdapter
from mpris_server.base import MAX_RATE, MIN_RATE, PlayState
from mpris_server.events import EventAdapter
from mpris_server import Metadata
from mpris_server.mpris.metadata import MetadataEntries

from providers import PathProvider


class QuantisAppAdapter(MprisAdapter):
    """Адаптер для плеера, реализующий интерфейс MPRIS."""

    def __init__(self, player):
        """Инициализирует адаптер и подключает сигналы плеера.

        Args:
            player: Экземпляр основного плеера.
        """
        self.player = player
        self._event_handler = None
        self._path_provider = PathProvider()

        player.track_changed.connect(self._on_track_changed)
        player.track_finished.connect(self._on_track_finished)

    def set_event_handler(self, handler) -> None:
        """Устанавливает обработчик событий для обновления метаданных по D-Bus.

        Args:
            handler: Экземпляр обработчика событий (QuantisEventHandler).
        """
        self._event_handler = handler

    def metadata(self) -> Metadata:
        """Возвращает метаданные текущего трека для MPRIS."""
        if not self.player.current_track:
            return Metadata(
                **{
                    MetadataEntries.TITLE: "",
                    MetadataEntries.TRACK_ID: "/org/mpris/MediaPlayer2/NoTrack",
                }
            )
            
        t = self.player.current_track
        length_us = max(0, self.player.duration) * 1000
        meta = {
            MetadataEntries.TRACK_ID: "/org/mpris/MediaPlayer2/track/1",
            MetadataEntries.TITLE: t.title,
            MetadataEntries.ARTISTS: [t.author],
            MetadataEntries.ALBUM: getattr(t, "album", None) or "Quantis",
            MetadataEntries.LENGTH: length_us,
        }
        
        art_url = self._art_url_for_track(t)
        if art_url:
            meta[MetadataEntries.ART_URL] = art_url
            
        return Metadata(**meta)

    def get_current_track(self):
        """Возвращает текущий трек. Оставлено None для совместимости с библиотекой."""
        return None

    def get_playstate(self) -> PlayState:
        """Возвращает текущее состояние воспроизведения."""
        if self.player.is_playing():
            return PlayState.PLAYING
        if self.player.current_track:
            return PlayState.PAUSED
        return PlayState.STOPPED

    def get_current_position(self) -> int:
        """Возвращает текущую позицию воспроизведения в микросекундах."""
        return self.player.time * 1000

    def get_rate(self) -> Decimal:
        """Возвращает текущую скорость воспроизведения."""
        return Decimal("1.0")

    def get_minimum_rate(self) -> float:
        """Возвращает минимальную скорость воспроизведения."""
        return MIN_RATE

    def get_maximum_rate(self) -> float:
        """Возвращает максимальную скорость воспроизведения."""
        return MAX_RATE

    def get_shuffle(self) -> bool:
        """Возвращает статус случайного воспроизведения."""
        return False

    def get_volume(self) -> Decimal:
        """Возвращает текущую громкость в диапазоне от 0.0 до 1.0."""
        vol = self.player.volume
        if vol is None or vol < 0:
            return Decimal("0")
        return Decimal(min(100, vol)) / Decimal("100")

    def get_stream_title(self) -> str:
        """Возвращает название текущего трека или стрима."""
        if self.player.current_track:
            return self.player.current_track.title
        return ""

    def _art_url_for_track(self, track) -> Optional[str]:
        """Формирует URI обложки трека (file:// или https://).

        Args:
            track: Экземпляр текущего трека.
        """
        if not track:
            return None
            
        cover_path = self._path_provider.get_cover_path(track)
        if os.path.isfile(cover_path):
            return "file://" + os.path.abspath(cover_path)
            
        if getattr(track, "source", "") == "youtube":
            return f"https://img.youtube.com/vi/{track.track_id}/hqdefault.jpg"
            
        return None

    def get_art_url(self, track) -> Optional[str]:
        """Возвращает URL обложки указанного трека."""
        target_track = track if track is not None else getattr(self.player, "current_track", None)
        return self._art_url_for_track(target_track)

    def is_mute(self) -> bool:
        """Возвращает статус беззвучного режима."""
        return self.player.volume <= 0

    def is_repeating(self) -> bool:
        """Возвращает статус повтора воспроизведения."""
        return False

    def is_playlist(self) -> bool:
        """Возвращает статус плейлиста."""
        return False

    def can_control(self) -> bool:
        """Указывает, возможно ли управление плеером."""
        return True

    def can_go_next(self) -> bool:
        """Указывает, доступен ли переход к следующему треку."""
        return True

    def can_go_previous(self) -> bool:
        """Указывает, доступен ли переход к предыдущему треку."""
        return True

    def can_pause(self) -> bool:
        """Указывает, доступна ли пауза."""
        return True

    def can_play(self) -> bool:
        """Указывает, доступно ли воспроизведение."""
        return True

    def can_seek(self) -> bool:
        """Указывает, доступна ли перемотка."""
        return True

    def can_quit(self) -> bool:
        """Указывает, можно ли закрыть плеер через MPRIS."""
        return False

    def can_raise(self) -> bool:
        """Указывает, можно ли вывести окно плеера на передний план."""
        return False

    def can_fullscreen(self) -> bool:
        """Указывает, поддерживается ли полноэкранный режим."""
        return False

    def has_tracklist(self) -> bool:
        """Указывает, поддерживает ли плеер список треков."""
        return False

    def can_edit_tracks(self) -> bool:
        """Указывает, можно ли редактировать список треков."""
        return False

    def get_desktop_entry(self) -> str:
        """Возвращает имя desktop-файла приложения."""
        return "neonmusic"

    def get_active_playlist(self) -> tuple:
        """Возвращает данные активного плейлиста."""
        return (False, ("/", "", ""))

    def get_tracks(self) -> list:
        """Возвращает список треков MPRIS."""
        return []

    def get_playlists(self, index: int, max_count: int, order: str, reverse: bool) -> list:
        """Возвращает список плейлистов MPRIS."""
        return []

    def _on_main_thread(self, fn: Callable) -> None:
        """Перенаправляет выполнение функции в главный поток Qt.

        Args:
            fn: Функция для выполнения.
        """
        QTimer.singleShot(0, fn)

    def play(self) -> None:
        """Возобновляет воспроизведение."""
        self._on_main_thread(self.player.resume)

    def pause(self) -> None:
        """Ставит воспроизведение на паузу."""
        self._on_main_thread(self.player.pause)

    def resume(self) -> None:
        """Продолжает воспроизведение."""
        self._on_main_thread(self.player.resume)

    def stop(self) -> None:
        """Останавливает воспроизведение."""
        self._on_main_thread(self.player.pause)

    def next(self) -> None:
        """Переключает на следующий трек."""
        self._on_main_thread(lambda: self.player.next_requested.emit())

    def previous(self) -> None:
        """Переключает на предыдущий трек."""
        self._on_main_thread(lambda: self.player.previous_requested.emit())

    def _notify_update(self) -> None:
        """Уведомляет D-Bus об изменении трека или состояния."""
        if self._event_handler:
            self._event_handler.on_title()
            self._event_handler.on_playback()

    def _on_track_changed(self, track) -> None:
        """Обрабатывает сигнал смены трека."""
        self._notify_update()

    def _on_track_finished(self) -> None:
        """Обрабатывает сигнал завершения трека."""
        self._notify_update()


class QuantisEventHandler(EventAdapter):
    """Обработчик событий D-Bus (MPRIS) для плеера."""

    def __init__(self, root, player):
        """Инициализирует обработчик событий.

        Args:
            root: Корневой объект D-Bus.
            player: Экземпляр плеера MPRIS.
        """
        super().__init__(root=root, player=player)

    def on_app_event(self, event: str) -> None:
        """Реагирует на внешние события от MPRIS.

        Args:
            event (str): Название события.
        """
        match event:
            case "play" | "pause":
                self.on_playpause()
            case "next":
                self.on_next()
            case "previous":
                self.on_previous()