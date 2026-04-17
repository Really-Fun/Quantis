import os
from decimal import Decimal

from PySide6.QtCore import QTimer

from mpris_server.adapters import MprisAdapter
from mpris_server.base import MAX_RATE, MIN_RATE, PlayState
from mpris_server.events import EventAdapter
from mpris_server.server import Server
from mpris_server import Metadata
from mpris_server.mpris.metadata import MetadataEntries

from providers import PathProvider


# --- Адаптер для Player ---
class NeonAppAdapter(MprisAdapter):
    def __init__(self, player):
        self.player = player
        self._event_handler = None

        player.track_changed.connect(self._on_track_changed)
        player.track_finished.connect(self._on_track_finished)

    def set_event_handler(self, handler):
        """Вызывать из main после создания NeonEventHandler — чтобы D-Bus получал обновления Metadata."""
        self._event_handler = handler

    # Обязательные методы (ключи — MetadataEntries). При отсутствии трека возвращаем
    # минимальные метаданные, иначе _get_metadata() даёт None и D-Bus ломается на пустом Metadata.
    def metadata(self) -> Metadata:
        if not self.player.current_track:
            return Metadata(
                **{
                    MetadataEntries.TITLE: "",
                    MetadataEntries.TRACK_ID: "/org/mpris/MediaPlayer2/NoTrack",
                }
            )
        t = self.player.current_track
        length_us = max(0, self.player.duration) * 1000  # ms -> µs
        meta = {
            MetadataEntries.TRACK_ID: "/org/mpris/MediaPlayer2/track/1",
            MetadataEntries.TITLE: t.title,
            MetadataEntries.ARTISTS: [t.author],
            MetadataEntries.ALBUM: getattr(t, "album", None) or "NeonMusic",
            MetadataEntries.LENGTH: length_us,
        }
        art_url = self._art_url_for_track(t)
        if art_url:
            meta[MetadataEntries.ART_URL] = art_url
        return Metadata(**meta)

    def get_current_track(self):
        # Не возвращаем наш Track — библиотека распаковывает его как свой Track tuple.
        return None

    def get_playstate(self) -> PlayState:
        if self.player.is_playing():
            return PlayState.PLAYING
        if self.player.current_track:
            return PlayState.PAUSED
        return PlayState.STOPPED

    def get_current_position(self) -> int:
        return self.player.time * 1000  # ms -> µs

    def get_rate(self):
        return Decimal("1.0")

    def get_minimum_rate(self):
        return MIN_RATE

    def get_maximum_rate(self):
        return MAX_RATE

    def get_shuffle(self) -> bool:
        return False

    def get_volume(self):
        vol = self.player.volume
        if vol is None or vol < 0:
            return Decimal("0")
        return Decimal(min(100, vol)) / Decimal("100")

    def get_stream_title(self):
        if self.player.current_track:
            return self.player.current_track.title
        return ""

    def _art_url_for_track(self, track) -> str | None:
        """URI обложки для MPRIS (file:// или https://)."""
        if not track:
            return None
        path_provider = PathProvider()
        cover_path = path_provider.get_cover_path(track)
        if os.path.isfile(cover_path):
            return "file://" + os.path.abspath(cover_path)
        if getattr(track, "source", "") == "youtube":
            return f"https://img.youtube.com/vi/{track.track_id}/hqdefault.jpg"
        return None

    def get_art_url(self, track) -> str | None:
        return self._art_url_for_track(
            track if track is not None else getattr(self.player, "current_track", None)
        )

    def is_mute(self) -> bool:
        return self.player.volume <= 0

    def is_repeating(self) -> bool:
        return False

    def is_playlist(self) -> bool:
        return False

    def can_control(self):
        return True

    def can_go_next(self) -> bool:
        return True

    def can_go_previous(self) -> bool:
        return True

    def can_pause(self) -> bool:
        return True

    def can_play(self) -> bool:
        return True

    def can_seek(self) -> bool:
        return True

    def can_quit(self):
        return False

    def can_raise(self) -> bool:
        return False

    def can_fullscreen(self) -> bool:
        return False

    def has_tracklist(self) -> bool:
        return False

    def can_edit_tracks(self):
        return False

    def get_desktop_entry(self):
        return "neonmusic"

    def get_active_playlist(self):
        # MAYBE_PLAYLIST = (valid: bool, (id, name, icon)); нельзя возвращать None — ломает GetAll.
        return (False, ("/", "", ""))

    def get_tracks(self):
        return []

    def get_playlists(self, index: int, max_count: int, order: str, reverse: bool):
        return []

    # Управление воспроизведением — вызывается из потока D-Bus, поэтому
    # переносим вызов в главный поток Qt (VLC/плеер живут там).
    def _on_main_thread(self, fn):
        QTimer.singleShot(0, fn)

    def play(self):
        self._on_main_thread(self.player.resume)

    def pause(self):
        self._on_main_thread(self.player.pause)

    def resume(self):
        self._on_main_thread(self.player.resume)

    def stop(self):
        self._on_main_thread(self.player.pause)

    def next(self):
        self._on_main_thread(lambda: self.player.next_requested.emit())

    def previous(self):
        self._on_main_thread(lambda: self.player.previous_requested.emit())

    # Сигналы
    def _on_track_changed(self, track):
        if self._event_handler:
            self._event_handler.on_title()
            self._event_handler.on_playback()

    def _on_track_finished(self):
        if self._event_handler:
            self._event_handler.on_title()
            self._event_handler.on_playback()


# --- Обработчик событий MPRIS ---
class NeonEventHandler(EventAdapter):
    def __init__(self, root, player):
        super().__init__(root=root, player=player)

    # Пример: реагируем на внешние события
    def on_app_event(self, event: str):
        if event == "pause":
            self.on_playpause()
        elif event == "play":
            self.on_playpause()
        elif event == "next":
            self.on_next()
        elif event == "previous":
            self.on_previous()
