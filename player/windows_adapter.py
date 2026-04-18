import asyncio

try:
    from winrt.windows.media.playback import MediaPlayer
    from winrt.windows.media import (
        MediaPlaybackType,
        MediaPlaybackStatus,
        SystemMediaTransportControlsButton,
    )
except ImportError:
    raise ImportError(
        "Для работы с Windows SMTC необходимо установить пакет winrt: "
        '"pip install winrt-Windows.media winrt-Windows.media.playback winrt-Windows.foundation"'  # Импорт обязательных модулей
    )

from models import Track
# Импортируй свой Player, если нужна строгая типизация (from player import Player)


class WindowsSMTCAdapter:
    """Адаптер интеграции плеера с системным оверлеем Windows (аналог MPRIS)."""

    def __init__(self, player, loop: asyncio.AbstractEventLoop = None):
        self.player = player
        self.loop = loop or asyncio.get_event_loop()

        self.system_player = MediaPlayer()
        self.smtc = self.system_player.system_media_transport_controls

        self.smtc.is_play_enabled = True
        self.smtc.is_pause_enabled = True
        self.smtc.is_next_enabled = True
        self.smtc.is_previous_enabled = True

        # Подписываемся на хардварные кнопки и нажатия в оверлее
        self.smtc.add_button_pressed(self._on_button_pressed)

        # Подписываемся на события твоего плеера
        self.player.track_changed.connect(self._on_track_changed)

    def _on_track_changed(self, track: Track) -> None:
        """Слушатель: автоматически обновляет данные в Windows при смене трека."""
        # Убедись, что у модели Track есть атрибуты title и artist.
        title = getattr(track, "title", "Unknown Title")
        artist = getattr(track, "artist", "Unknown Artist")

        self.update_metadata(title, artist)
        self.update_playback_status(True)

    def update_metadata(self, title: str, artist: str) -> None:
        """Обновляет название трека и автора в оверлее Windows."""
        updater = self.smtc.display_updater
        updater.type = MediaPlaybackType.MUSIC

        updater.music_properties.title = title
        updater.music_properties.artist = artist

        updater.update()

    def update_playback_status(self, is_playing: bool) -> None:
        """Обновляет иконку Play/Pause в оверлее."""
        if is_playing:
            self.smtc.playback_status = MediaPlaybackStatus.PLAYING
        else:
            self.smtc.playback_status = MediaPlaybackStatus.PAUSED

    def _on_button_pressed(self, sender, args) -> None:
        """
        Обработчик нажатий (вызывается Windows в отдельном COM-потоке).
        Используем call_soon_threadsafe для безопасного вызова в основном event loop.
        """
        button = args.button

        if button == SystemMediaTransportControlsButton.PLAY:
            self.loop.call_soon_threadsafe(self.player.resume)
            self.update_playback_status(True)

        elif button == SystemMediaTransportControlsButton.PAUSE:
            self.loop.call_soon_threadsafe(self.player.pause)
            self.update_playback_status(False)

        elif button == SystemMediaTransportControlsButton.NEXT:
            # Эмитим сигнал PySide, чтобы логика очереди отработала штатно
            self.loop.call_soon_threadsafe(self.player.next_requested.emit)

        elif button == SystemMediaTransportControlsButton.PREVIOUS:
            self.loop.call_soon_threadsafe(self.player.previous_requested.emit)
