from mpris_server.adapters import MprisAdapter
from mpris_server.events import EventAdapter
from mpris_server.server import Server
from mpris_server import Metadata


# --- Адаптер для Player ---
class NeonAppAdapter(MprisAdapter):
    def __init__(self, player):
        self.player = player
        self._current_track = None

        player.track_changed.connect(self._on_track_changed)
        player.track_finished.connect(self._on_track_finished)

    # Обязательные методы
    def metadata(self) -> Metadata:
        if not self._current_track:
            return Metadata()
        return Metadata(
            trackid="/org/mpris/MediaPlayer2/track/1",
            title=self._current_track.title,
            artist=[self._current_track.artist],
            album=self._current_track.album,
            length=max(0, self.player.duration) * 1000,  # микросекунды
        )

    def get_current_track(self):
        return self._current_track

    def get_playback_status(self):
        return "Playing" if self.player.is_playing() else "Paused"

    def get_position(self):
        return self.player.time * 1000  # ms -> µs

    def can_control(self):
        return True

    def can_quit(self):
        return False

    def can_edit_tracks(self):
        return False

    def get_desktop_entry(self):
        return "neonmusic"

    def get_active_playlist(self):
        return None

    # Управление воспроизведением
    def play(self):
        self.player.resume()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.pause()

    # Сигналы
    def _on_track_changed(self, track):
        self._current_track = track

    def _on_track_finished(self):
        self._current_track = None


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