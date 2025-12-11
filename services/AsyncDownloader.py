from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from asyncio import get_running_loop
import aiohttp

from config import GetClients
from models.Tracks import YandexTrack, YoutubeTrack
from providers import PathProvider

from yt_dlp import YoutubeDL

class AsyncDownloaderInterface(ABC):
    
    @abstractmethod
    async def download_track(self, track: YandexTrack | YoutubeTrack) -> None:
        ...
    
    @abstractmethod
    async def download_cover(self, track: YandexTrack | YoutubeTrack) -> None:
        ...
        

class AsyncYandexDownloader(AsyncDownloaderInterface):
    
    def __init__(self):
        self.path_provider = PathProvider()
        self.client = GetClients().get_yandex_client()
    
    async def download_track(self, track: YandexTrack | YoutubeTrack) -> None:
        try:
            track_info = await self.client.tracks(track.track_id)
            await track_info[0].download_async(self.path_provider.get_track_path(track))
        except:
            print("Тут должен быть дебаг")

    async def get_stream_url(self, track: YandexTrack) -> str:
        try:
            track_info = await self.client.tracks(track.track_id)
            download_info = await track_info[0].get_download_info_async()
            url = await download_info[0].get_direct_link_async()
            return url
        except:
            print("Тут должен быть дебаг")

    async def download_cover(self, track: YandexTrack | YoutubeTrack) -> None:
        try:
            track_info = await self.client.tracks(track.track_id)
            await track_info[0].downloadCoverAsync(self.path_provider.get_cover_path(track))
        except:
            print("Тут должен быть дебаг")
        
class AsyncYoutubeDownloader(AsyncDownloaderInterface):
    
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
        self.path_provider = PathProvider()

    async def get_stream_url(self, track : YoutubeTrack) -> str:
        ydl_opts = {**self.opts, "format": "m4a/bestaudio[ext=m4a]", "skip_download": True}
        with ThreadPoolExecutor() as pool:
            url = await get_running_loop().run_in_executor(pool, self.sync_stream,self.yt, track.track_id)
        return url
    
    async def download_track(self, track: YoutubeTrack) -> None:
        self.opts["outtmpl"] = f"assets/music/{track.track_id}.%(ext)s"
        with ThreadPoolExecutor() as pool:
            await get_running_loop().run_in_executor(pool, self.sync_download, self.opts, track.track_id) 
        track.track_path = self.opts["outtmpl"]
            
    async def download_cover(self, track: YandexTrack) -> None:
        cover_url = f"https://img.youtube.com/vi/{track.track_id}/hqdefault.jpg"
        track.cover_path = f"assets/covers/{track.track_id}.jpg"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(cover_url) as response:
                if response.status != 200:
                    pass
                data = await response.read()
                
                with open(track.cover_path, "wb") as file:
                    file.write(data)
    
    @staticmethod
    def sync_download(opts: dict, track_id: str) -> None:
        try:
            with YoutubeDL(opts) as ydl:
                ydl.extract_info(
                    f"https://youtube.com/watch?v={track_id}",
                    download=True
                )
        except:
            pass

    @staticmethod
    def sync_stream(yt, track_id: str) -> str:
        info = yt.extract_info(
                    f"https://www.youtube.com/watch?v={track_id}", download=False
                )
        url = info.get("url")
        if url:
            return url