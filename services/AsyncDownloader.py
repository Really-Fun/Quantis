from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from asyncio import get_running_loop

from config import GetClients
from models.Tracks import Track
from providers import PathProvider

import aiohttp
from yt_dlp import YoutubeDL

class AsyncDownloaderInterface(ABC):
    """Абстрактный класс для Downloader'ов"""
    
    @abstractmethod
    async def download_track(self, track: Track) -> None:
        ...
    
    @abstractmethod
    async def download_cover(self, track: Track) -> None:
        ...
        

class AsyncYandexDownloader(AsyncDownloaderInterface):
    """Класс для асинхронного скачивания треков и обложек с яндекса"""

    def __init__(self):
        self.path_provider = PathProvider()
        self.client = GetClients().get_yandex_client()
    
    async def download_track(self, track: Track) -> None:
        try:
            track_info = await self.client.tracks(track.track_id)
            await track_info[0].download_async(self.path_provider.get_track_path(track))
        except:
            print("Тут должен быть дебаг")

    async def download_cover(self, track: Track) -> None:
        try:
            track_info = await self.client.tracks(track.track_id)
            await track_info[0].downloadCoverAsync(self.path_provider.get_cover_path(track), "200x200")
        except BaseException as error:
            print("Тут должен быть дебаг", error)
        
class AsyncYoutubeDownloader(AsyncDownloaderInterface):
    """Класс для асинхронного скачивания треков и обложек с ютуба"""
    
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
    
    async def download_track(self, track: Track) -> None:
        self.opts["outtmpl"] = f"assets/music/{track.track_id}.%(ext)s"
        with ThreadPoolExecutor() as pool:
            await get_running_loop().run_in_executor(pool, self.sync_download, self.opts, track.track_id) 
        track.track_path = self.opts["outtmpl"]
            
    async def download_cover(self, track: Track) -> None:
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
            print("Тут должен быть дебаг!!!")


class AsyncDownloader(AsyncDownloaderInterface):

    def __init__(self):
        self._yandex_downloader = AsyncYandexDownloader()
        self._youtube_downloader = AsyncYoutubeDownloader()

    async def download_track(self, track: Track) -> None:
        match track.source:
            case "yandex":
                await self._yandex_downloader.download_track(track)
            case "youtube":
                await self._youtube_downloader.download_track(track)

    async def download_cover(self, track: Track) -> None:
        match track.source:
            case "yandex":
                await self._yandex_downloader.download_cover(track)
            case "youtube":
                await  self._youtube_downloader.download_cover(track)