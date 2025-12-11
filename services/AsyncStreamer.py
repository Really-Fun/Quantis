from abc import ABC, abstractmethod
from asyncio import get_running_loop
from concurrent.futures import ThreadPoolExecutor

from config import GetClients
from models import Track

from yt_dlp import YoutubeDL


class AsyncStreamerInterface(ABC):

    @abstractmethod
    async def get_stream_url(self, track: Track) -> str | None:
        ...

class AsyncYandexStreamer(AsyncStreamerInterface):

    def __init__(self):
        self.client = GetClients().get_yandex_client()

    async def get_stream_url(self, track: Track) -> str | None:
            try:
                track_info = await self.client.tracks(track.track_id)
                download_info = await track_info[0].get_download_info_async()
                url = await download_info[0].get_direct_link_async()
                return url
            except:
                print("Тут должен быть дебаг")
                return None

class AsyncYoutubeStreamer(AsyncStreamerInterface):

    def __init__(self):
        self.opts = {
            "quiet": True,
            "noplaylist": True,
            "extract_flat": False,
            "no_warnings": True,
            "nocheckcertificate": True,
            "format": "bestaudio",
            "postprocessors": [],
        }
        adv_opts = self.opts
        adv_opts["skip_download"] = True
        self.yt = YoutubeDL(adv_opts)

    async def get_stream_url(self, track: Track) -> str:
        ydl_opts = {**self.opts, "format": "m4a/bestaudio[ext=m4a]", "skip_download": True}
        with ThreadPoolExecutor() as pool:
            url = await get_running_loop().run_in_executor(pool, self.sync_stream, self.yt, track.track_id)
        return url

    @staticmethod
    def sync_stream(yt, track_id: str) -> str:
        info = yt.extract_info(
            f"https://www.youtube.com/watch?v={track_id}", download=False
        )
        url = info.get("url")
        if url:
            return url