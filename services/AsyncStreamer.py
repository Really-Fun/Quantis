from abc import ABC, abstractmethod
from asyncio import get_running_loop
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from time import time

from config import GetClients
from models import Track

from yt_dlp import YoutubeDL


def url_cache(func):
    urls = {}

    @wraps(func)
    async def wrapper(*args, **kwargs):
        nonlocal urls
        if len(args) == 1:
            track = kwargs['track']
        else:
            track = args[1]
        track_url = urls.get(track.track_id, None)
        if (track_url is None) or (time() - track_url[1] >= 30 * 60):
            track_url = urls[track.track_id] = (await func(*args, **kwargs), time())
        return track_url[0]

    return wrapper

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
        with ThreadPoolExecutor() as pool:
            url = await get_running_loop().run_in_executor(pool, self.sync_stream, self.yt, track.track_id)
        return url

    @staticmethod
    def sync_stream(yt, track_id: str) -> str:
        info = yt.extract_info(
            f"https://www.youtube.com/watch?v={track_id}", download=False
        )
        url = info.get("url")
        return url


class AsyncStreamer(AsyncStreamerInterface):

    def __init__(self):
        self._async_yandex_streamer = AsyncYandexStreamer()
        self._async_youtube_streamer = AsyncYoutubeStreamer()

    @url_cache
    async def get_stream_url(self, track: Track) -> str | None:
        match track.source:
            case "youtube":
                url = await self._async_youtube_streamer.get_stream_url(track)
                return url
            case "yandex":
                url = await self._async_yandex_streamer.get_stream_url(track)
                return url
            case _:
                raise NameError("Неизвестный source  у трека")