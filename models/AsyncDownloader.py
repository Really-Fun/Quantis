from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from asyncio import get_running_loop
import aiohttp

from config import GetClients
from models.Tracks import YandexTrack, YoutubeTrack
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
        self.client = GetClients().get_yandex_client()
    
    async def download_track(self, track: YandexTrack | YoutubeTrack) -> None:
        try:
            track_info = await self.client.tracks(track.track_id)
            await track_info[0].download_async(track.track_path)
        except:
            pass
        
    async def download_cover(self, track: YandexTrack | YoutubeTrack) -> None:
        try:
            track_info = await self.client.tracks(track.track_id)
            await track_info[0].downloadCoverAsync(track.cover_path)
        except:
            pass
        
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
    
    async def download_track(self, track: YandexTrack | YoutubeTrack) -> None:
        self.opts["outtmpl"] = f"assets/music/{track.track_id}.%(ext)s"
        with ThreadPoolExecutor() as pool:
            await get_running_loop().run_in_executor(pool, self.sync_download, self.opts, track.track_id) 
        track.track_path = self.opts["outtmpl"]
            
    async def download_cover(self, track: YandexTrack | YandexTrack) -> None:
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