try:
    from winrt.windows.media import (
        MediaPlaybackStatus,
        MediaPlaybackType,
        SystemMediaTransportControlsButton,
    )
    from winrt.windows.media.playback import MediaPlayer
except ImportError as exc:
    raise ImportError(
        "Для работы с Windows SMTC необходимо установить пакет winrt: "
        '"pip install winrt-Windows.media winrt-Windows.media.playback winrt-Windows.foundation"'
    ) from exc

from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track


class WindowsSMTCAdapter:
    """Адаптер интеграции плеера с системным оверлеем Windows (аналог MPRIS)."""

    def __init__(self, player, bridge: AsyncBridge, event_bus):
        self.player = player
        self._bridge = bridge
        self._event_bus = event_bus

        self.system_player = MediaPlayer()
        self.smtc = self.system_player.system_media_transport_controls

        self.smtc.is_play_enabled = True
        self.smtc.is_pause_enabled = True
        self.smtc.is_next_enabled = True
        self.smtc.is_previous_enabled = True

        self.smtc.add_button_pressed(self._on_button_pressed)

        event_bus.subscribe("track_changed", self._on_track_changed)

    def _on_track_changed(self, track: Track = None, **kwargs) -> None:
        title = getattr(track, "title", "Unknown Title")
        artist = getattr(track, "author", "Unknown Artist")

        self.update_metadata(title, artist)
        self.update_playback_status(True)

    def update_metadata(self, title: str, artist: str) -> None:
        updater = self.smtc.display_updater
        updater.type = MediaPlaybackType.MUSIC

        updater.music_properties.title = title
        updater.music_properties.artist = artist

        updater.update()

    def update_playback_status(self, is_playing: bool) -> None:
        if is_playing:
            self.smtc.playback_status = MediaPlaybackStatus.PLAYING
        else:
            self.smtc.playback_status = MediaPlaybackStatus.PAUSED

    def _on_button_pressed(self, sender, args) -> None:
        button = args.button

        if button == SystemMediaTransportControlsButton.PLAY:
            self._bridge.invoke_main(self.player.resume)
            self.update_playback_status(True)

        elif button == SystemMediaTransportControlsButton.PAUSE:
            self._bridge.invoke_main(self.player.pause)
            self.update_playback_status(False)

        elif button == SystemMediaTransportControlsButton.NEXT:
            self._bridge.invoke_main(self._event_bus.next_requested.emit)

        elif button == SystemMediaTransportControlsButton.PREVIOUS:
            self._bridge.invoke_main(self._event_bus.previous_requested.emit)
