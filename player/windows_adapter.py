import asyncio

from winsdk.windows.media.playback import MediaPlayer
from winsdk.windows.media import MediaPlaybackType, MediaPlaybackStatus
from winsdk.windows.media.control import SystemMediaTransportControlsButton

class WindowsSMTCAdapter:
    def __init__(self, player, loop: asyncio.AbstractEventLoop):
        self.player = player
        self.loop = loop
        
        self.system_player = MediaPlayer()
        self.smtc = self.system_player.system_media_transport_controls
        
        self.smtc.is_play_enabled = True
        self.smtc.is_pause_enabled = True
        self.smtc.is_next_enabled = True
        self.smtc.is_previous_enabled = True
        
        self.smtc.add_button_pressed(self._on_button_pressed)

    def update_metadata(self, title: str, artist: str):
        """Обновляет название трека и автора в оверлее Windows."""
        updater = self.smtc.display_updater
        updater.type = MediaPlaybackType.MUSIC
        
        updater.music_properties.title = title
        updater.music_properties.artist = artist
        
        updater.update()

    def update_playback_status(self, is_playing: bool):
        """Обновляет иконку Play/Pause в оверлее."""
        if is_playing:
            self.smtc.playback_status = MediaPlaybackStatus.PLAYING
        else:
            self.smtc.playback_status = MediaPlaybackStatus.PAUSED

    def _on_button_pressed(self, sender, args):
        """Обработчик нажатий (вызывается Windows в отдельном потоке)."""
        button = args.button
        
        if button == SystemMediaTransportControlsButton.PLAY:
            self.loop.call_soon_threadsafe(self.player.resume)
        elif button == SystemMediaTransportControlsButton.PAUSE:
            self.loop.call_soon_threadsafe(self.player.pause)
        elif button == SystemMediaTransportControlsButton.NEXT:
            self.loop.call_soon_threadsafe(self.player.play_track)
        elif button == SystemMediaTransportControlsButton.PREVIOUS:
            self.loop.call_soon_threadsafe(self.player.play_track) 