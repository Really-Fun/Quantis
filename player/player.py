import asyncio

from PySide6.QtCore import QObject, Signal
from qasync import asyncSlot
from vlc import Instance

from models import Track
from providers import PathProvider
from services import AsyncStreamer


class Player(QObject):
    track_finished = Signal()
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        super().__init__()
        self.vlc_instance = Instance()
        self.media_player = self.vlc_instance.media_player_new()
        self.current_track = None
        self.current_loaded_track = None
        self.repeat = False
        self.on_pause = False
        self.path_provider = PathProvider()
        self.async_streamer = AsyncStreamer()

    def pause(self):
        self.on_pause = True
        self.media_player.pause()

    @asyncSlot()
    async def play_track(self, track: Track) -> None:
        """Проигрывает переданный трек"""

        self.on_pause = False
        self.current_track = track

        if track.downloaded:
            try:
               path = self.path_provider.get_track_path(track)
               loaded_track = self.vlc_instance.media_new(path)
            except FileNotFoundError:
                print("DEBUG(Трек не скачан)")
        else:
            stream_url = await self.async_streamer.get_stream_url(track)
            loaded_track = self.vlc_instance.media_new(stream_url)

        self.media_player.set_media(loaded_track)
        self.media_player.play()