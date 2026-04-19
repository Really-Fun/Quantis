from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from asyncio import get_running_loop
from typing import Callable, TypeVar, Any
from pathlib import Path
import functools
import logging

from config import Clients
from models.Tracks import Track, YandexTrack, YoutubeTrack
from providers import PathProvider

from yt_dlp import YoutubeDL
import aiohttp


F = TypeVar("F", bound=Callable[..., Any])
logger = logging.getLogger(__name__)


def log(method: F) -> F:
    logger = logging.getLogger(method.__module__)

    @functools.wraps(method)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug(f"Entering: {method.__name__}")

        result = await method(*args, **kwargs)
        logger.debug(result)

        logger.debug(f"Exiting: {method.__name__}")

        return result

    return wrapper


class AsyncDownloaderInterface(ABC):
    """Абстрактный класс для Downloader'ов"""

    @abstractmethod
    async def download_track(self, track: Track) -> None: ...

    @abstractmethod
    async def download_cover(self, track: Track) -> None: ...


class AsyncYandexDownloader(AsyncDownloaderInterface):
    """Класс для асинхронного скачивания треков и обложек с яндекса"""

    def __init__(self):
        self.path_provider = PathProvider()
        self.client = Clients().get_yandex_client()

    async def download_track(self, track: YandexTrack) -> None:
        """Скачивает трек с яндекса. Асинхронное скачивание

        Args:
            track (YandexTrack): Трек с Яндекса
        """
        if self.client is None:
            return
        try:
            track_info = await self.client.tracks(track.track_id)
            current_track = track_info[0]
            file_path = self.path_provider.get_track_path(track)

            is_authorized = bool(getattr(self.client, "token", None))

            if is_authorized:
                await current_track.download_async(file_path)
            else:
                await current_track.download_async(file_path, bitrate_in_kbps=192)
        except Exception:
            logger.exception("Не удалось скачать трек с Яндекс.Музыки: %s", track)

    async def download_cover(self, track: YandexTrack) -> None:
        """Скачивает обложку трека с платформы Яндекс. Асинхронное скачивание

        Args:
            track (YandexTrack): Трек с Яндекса
        """
        if self.client is None:
            return
        try:
            track_info = await self.client.tracks(track.track_id)
            await track_info[0].downloadCoverAsync(
                self.path_provider.get_cover_path(track), "200x200"
            )
        except Exception:
            logger.exception("Не удалось скачать обложку с Яндекс.Музыки: %s", track)


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
        self.path_provider = PathProvider()
        self._executor = ThreadPoolExecutor(max_workers=10)

    async def download_track(self, track: YoutubeTrack) -> None:
        """Асинхронная функция для скачивания трека с ютуба.
        Основана на ThreadPoolExecutor и синхронном скачивании с ytdlp

        Args:
            track (YoutubeTrack): трек с Ютуба
        """
        self.opts["outtmpl"] = self.path_provider.get_track_path(
            track, extension="%(ext)s"
        )
        await get_running_loop().run_in_executor(
            self._executor, self.sync_download, self.opts, track.track_id
        )
        track.track_path = self.opts["outtmpl"]

    async def download_cover(self, track: YoutubeTrack) -> None:
        """Асинхронное получение обложки с ютуб.

        Args:
            track (YoutubeTrack): Трек с Ютуба
        """
        cover_url = f"https://img.youtube.com/vi/{track.track_id}/hqdefault.jpg"
        track.cover_path = self.path_provider.get_cover_path(track)

        async with aiohttp.ClientSession() as session:  # noqa Создаём сессию но не используем, может лучше создать 1 глобальную?
            async with self._session.session.get(cover_url) as response:
                if response.status != 200:
                    return
                data = await response.read()

                Path(track.cover_path).parent.mkdir(parents=True, exist_ok=True)
                with open(track.cover_path, "wb") as file:
                    file.write(data)

    @staticmethod
    def sync_download(opts: dict, track_id: str) -> None:
        try:
            with YoutubeDL(opts) as ydl:
                ydl.extract_info(
                    f"https://youtube.com/watch?v={track_id}", download=True
                )
        except Exception:
            logger.exception("Не удалось скачать трек с YouTube: %s", track_id)


class AsyncDownloader(AsyncDownloaderInterface):
    def __init__(self):
        self._yandex_downloader = AsyncYandexDownloader()
        self._youtube_downloader = AsyncYoutubeDownloader()

    @log
    async def download_track(self, track: Track) -> None:
        match track.source:
            case "yandex":
                await self._yandex_downloader.download_track(track)
            case "youtube":
                await self._youtube_downloader.download_track(track)

    @log
    async def download_cover(self, track: Track) -> None:
        match track.source:
            case "yandex":
                await self._yandex_downloader.download_cover(track)
            case "youtube":
                await self._youtube_downloader.download_cover(track)
