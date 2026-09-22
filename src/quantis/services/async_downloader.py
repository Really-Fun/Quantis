"""Асинхронное скачивание (треков, обложек)
Наследуется абстрактный класс
Yandex
Youtube"""

import logging
from abc import ABC, abstractmethod
from asyncio import Semaphore, get_running_loop
from pathlib import Path
from typing import Optional

import aiofiles
import aiohttp

from quantis.config import Clients
from quantis.models.track import (
    SoundCloudTrack,
    Track,
    TrackSource,
    YandexTrack,
    YoutubeTrack,
)
from quantis.providers import PathProvider
from quantis.services.cover_validate import cover_bytes_ok, cover_file_ok
from quantis.services.wallpaper_policy import (
    wallpaper_cache_format,
    wallpaper_duration_filter,
)

logger = logging.getLogger(__name__)

_AUDIO_FORMAT = (
    "ba[ext=m4a]/ba[ext=mp3]/"
    "bestaudio[ext=m4a]/bestaudio[ext=mp3]/"
    "bestaudio[protocol=https]/bestaudio"
)
_VIDEO_FORMAT = wallpaper_cache_format(360)
_AUDIO_EXTENSIONS = frozenset({"m4a", "mp3"})
_MAX_COVER_BYTES = 8 * 1024 * 1024


def _is_http_url(url: str) -> bool:
    return url.startswith("https://") or url.startswith("http://")


async def _read_http_body(response: aiohttp.ClientResponse, limit: int) -> bytes | None:
    expected = response.content_length
    data = await response.read()
    if not data or len(data) > limit:
        return None
    if expected is not None and len(data) < expected:
        return None
    return data


async def _write_cover_file(path: str, data: bytes) -> bool:
    if not cover_bytes_ok(data):
        return False
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    async with aiofiles.open(tmp, "wb") as file:
        await file.write(data)
    tmp.replace(dest)
    return True


class AsyncDownloaderInterface(ABC):
    """Абстрактный класс для Downloader'ов"""

    @abstractmethod
    async def download_track(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> None: ...

    @abstractmethod
    async def download_cover(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> None: ...


class AsyncYandexDownloader(AsyncDownloaderInterface):
    """Класс для асинхронного скачивания треков и обложек с яндекса"""

    def __init__(self) -> None:
        self.path_provider = PathProvider()
        self._client = None
        self._client_ready = False

    @property
    def client(self):
        if not self._client_ready:
            self._client = Clients().get_yandex_client()
            self._client_ready = True
        return self._client

    async def download_track(self, track: Track | YandexTrack | YoutubeTrack) -> None:
        """Скачивает трек с яндекса. Асинхронное скачивание

        Args:
            track (YandexTrack): Трек с Яндекса
        """
        if self.client is None:
            logger.warning(
                "Клиент ЯндексМузыки не инициализирован." "Невозможно скачать трек: %s",
                track,
            )
            return
        try:
            PathProvider.ensure_storage_dirs()
            track_info = await self.client.tracks(int(track.track_id))
            current_track = track_info[0]
            file_path = self.path_provider.get_track_path(track)

            is_authorized = bool(getattr(self.client, "token", None))

            if is_authorized:
                # Полный битрейт — не preview
                await current_track.download_async(file_path, bitrate_in_kbps=320)
            else:
                await current_track.download_async(file_path, bitrate_in_kbps=192)
        except Exception:
            logger.exception("Не удалось скачать трек с Яндекс.Музыки: %s", track)

    async def download_cover(self, track: Track | YandexTrack | YoutubeTrack) -> None:
        """Скачивает обложку трека с платформы Яндекс. Асинхронное скачивание

        Args:
            track (YandexTrack): Трек с Яндекса
        """
        if self.client is None:
            logger.warning(
                "Клиент ЯндексМузыки не инициализирован." "Невозможно скачать трек: %s",
                track,
            )
            return
        try:
            PathProvider.ensure_storage_dirs()
            track_info = await self.client.tracks(int(track.track_id))
            dest = self.path_provider.get_cover_path(track)
            await track_info[0].downloadCoverAsync(dest, "400x400")
            if not cover_file_ok(dest):
                logger.warning("Обложка Яндекса обрезана или пустая: %s", track)
        except Exception:
            logger.exception("Не удалось скачать обложку с Яндекс.Музыки: %s", track)


class AsyncYoutubeDownloader(AsyncDownloaderInterface):
    """Класс для асинхронного скачивания треков и обложек с ютуба"""

    def __init__(self) -> None:
        self._base_opts = {
            "quiet": True,
            "noplaylist": True,
            "extract_flat": False,
            "no_warnings": True,
            "postprocessors": [],
        }
        self.path_provider = PathProvider()
        from quantis.core.worker_pool import get_worker_pool

        self._executor = get_worker_pool()
        self._owns_executor = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = Semaphore(value=8)

    def _ydl_opts(self, outtmpl: str, *, video: bool = False) -> dict:
        opts = {
            **self._base_opts,
            "outtmpl": outtmpl,
            "format": self._video_format() if video else _AUDIO_FORMAT,
            "extractor_args": {"youtube": {"player_client": ["android"]}},
        }
        if video:
            opts["match_filter"] = wallpaper_duration_filter
        return opts

    def _ydl_opts_fallback(self, outtmpl: str, *, video: bool = False) -> dict:
        from quantis.config.credentials import youtube_yt_dlp_cookiefile

        opts = {
            **self._base_opts,
            "outtmpl": outtmpl,
            "format": self._video_format() if video else _AUDIO_FORMAT,
        }
        if video:
            opts["match_filter"] = wallpaper_duration_filter
        cookiefile = youtube_yt_dlp_cookiefile()
        if cookiefile:
            opts["cookiefile"] = cookiefile
        return opts

    @staticmethod
    def _video_format() -> str:
        from quantis.ui.preferences import UiPreferences

        return wallpaper_cache_format(UiPreferences().dynamic_wallpaper_quality)

    @staticmethod
    def _video_wallpaper_enabled() -> bool:
        from quantis.ui.preferences import UiPreferences

        return UiPreferences().dynamic_wallpaper_enabled

    def _audio_outtmpl(self, track: Track | YoutubeTrack) -> str:
        return self.path_provider.get_track_path(track, extension="%(ext)s")

    def _apply_downloaded_extension(self, track: Track | YoutubeTrack) -> str | None:
        prefix = f"{track.track_id}_"
        music_dir = Path(self.path_provider.MUSIC_FOLDER)
        for candidate in music_dir.glob(f"{prefix}*"):
            ext = candidate.suffix.lstrip(".").lower()
            if ext in _AUDIO_EXTENSIONS:
                if isinstance(track, YoutubeTrack):
                    track.extension = ext
                return ext
        return None

    async def _download_audio(self, track: Track | YoutubeTrack) -> bool:
        outtmpl = self._audio_outtmpl(track)
        for opts in (
            self._ydl_opts(outtmpl, video=False),
            self._ydl_opts_fallback(outtmpl, video=False),
        ):
            try:
                await get_running_loop().run_in_executor(
                    self._executor, self.sync_download, opts, track.track_id
                )
                return self._apply_downloaded_extension(track) is not None
            except Exception:
                logger.debug(
                    "YouTube audio download attempt failed for %s",
                    track.track_id,
                    exc_info=True,
                )
        return False

    async def _download_video_cache(self, track: Track | YoutubeTrack) -> None:
        outtmpl = self.path_provider.get_video_cache_path(track, extension="%(ext)s")
        for opts in (
            self._ydl_opts(outtmpl, video=True),
            self._ydl_opts_fallback(outtmpl, video=True),
        ):
            try:
                await get_running_loop().run_in_executor(
                    self._executor, self.sync_download, opts, track.track_id
                )
                return
            except Exception:
                logger.debug(
                    "YouTube video cache download failed for %s",
                    track.track_id,
                    exc_info=True,
                )
        logger.warning("Не удалось скачать видео-кэш для обоев: %s", track.track_id)

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def download_track(self, track: Track | YandexTrack | YoutubeTrack) -> None:
        """Скачивает аудио (m4a/mp3). MP4 — только в кэш обоев при включённом видеофоне."""
        if not await self._download_audio(track):
            logger.error("Не удалось скачать трек с YouTube: %s", track.track_id)
            return
        if self._video_wallpaper_enabled():
            await self._download_video_cache(track)

    async def download_cover(self, track: Track | YandexTrack | YoutubeTrack) -> None:
        """Асинхронное получение обложки с ютуб.

        Args:
            track (YoutubeTrack): Трек с Ютуба
        """
        cover_path = self.path_provider.get_cover_path(track)
        session = await self.get_session()
        thumbs = ("maxresdefault.jpg", "sddefault.jpg", "hqdefault.jpg")

        async with self._semaphore:
            try:
                for name in thumbs:
                    cover_url = f"https://img.youtube.com/vi/{track.track_id}/{name}"
                    async with session.get(cover_url) as response:
                        if response.status != 200:
                            continue
                        data = await _read_http_body(response, _MAX_COVER_BYTES)
                        if data is None:
                            continue
                        if await _write_cover_file(cover_path, data):
                            return
            except aiohttp.ClientError:
                logger.exception("Ошибка при скачивании обложки для %s", track.track_id)

    @staticmethod
    def sync_download(opts: dict, track_id: int | str) -> None:
        from yt_dlp import YoutubeDL

        from quantis.services.url_resolver import is_youtube_video_id

        if not is_youtube_video_id(str(track_id)):
            raise ValueError(f"Некорректный YouTube id: {track_id!r}")

        with YoutubeDL(opts) as ydl:
            ydl.extract_info(f"https://youtube.com/watch?v={track_id}", download=True)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    def shutdown(self) -> None:
        # Общий worker pool останавливает MusicService.
        return


class AsyncSoundCloudDownloader(AsyncDownloaderInterface):
    """Скачивание треков и обложек SoundCloud через yt-dlp."""

    def __init__(self) -> None:
        self.path_provider = PathProvider()
        from quantis.core.worker_pool import get_worker_pool

        self._executor = get_worker_pool()
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = Semaphore(value=8)

    def _ydl_opts(self, outtmpl: str) -> dict:
        return {
            "quiet": True,
            "noplaylist": True,
            "extract_flat": False,
            "no_warnings": True,
            "outtmpl": outtmpl,
            "format": (
                "http_mp3_128/bestaudio[format_id!*=preview][ext=mp3]/"
                "bestaudio[format_id!*=preview]/bestaudio"
            ),
        }

    def _apply_downloaded_extension(self, track: Track) -> str | None:
        prefix = f"{self.path_provider.storage_id(track)}_"
        music_dir = Path(
            self.path_provider.MUSIC_FOLDER or self.path_provider.music_folder()
        )
        for candidate in music_dir.glob(f"{prefix}*"):
            ext = candidate.suffix.lstrip(".").lower()
            if ext in _AUDIO_EXTENSIONS:
                if isinstance(track, SoundCloudTrack):
                    track.extension = ext
                return ext
        return None

    async def download_track(self, track: Track | YandexTrack | YoutubeTrack) -> None:
        from quantis.services.soundcloud import watch_url

        outtmpl = self.path_provider.get_track_path(track, extension="%(ext)s")
        PathProvider.ensure_storage_dirs()
        try:
            await get_running_loop().run_in_executor(
                self._executor,
                self.sync_download,
                self._ydl_opts(outtmpl),
                watch_url(track.track_id),
            )
        except Exception:
            logger.exception("Не удалось скачать трек с SoundCloud: %s", track.track_id)
            return
        if self._apply_downloaded_extension(track) is None:
            logger.error("Не удалось скачать трек с SoundCloud: %s", track.track_id)

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def download_cover(self, track: Track | YandexTrack | YoutubeTrack) -> None:
        cover_url = ""
        if isinstance(track, SoundCloudTrack):
            cover_url = track.thumbnail_url
        if not cover_url:
            cover_url = await get_running_loop().run_in_executor(
                self._executor, self._sync_thumbnail, str(track.track_id)
            )
        if not cover_url or not _is_http_url(cover_url):
            return

        cover_path = self.path_provider.get_cover_path(track)
        session = await self.get_session()
        async with self._semaphore:
            try:
                async with session.get(cover_url) as response:
                    if response.status != 200:
                        return
                    data = await _read_http_body(response, _MAX_COVER_BYTES)
                    if data is None:
                        return
                    await _write_cover_file(cover_path, data)
            except aiohttp.ClientError:
                logger.exception(
                    "Ошибка при скачивании обложки SoundCloud для %s",
                    track.track_id,
                )

    @staticmethod
    def _sync_thumbnail(track_id: str) -> str:
        from yt_dlp import YoutubeDL

        from quantis.services.soundcloud import track_from_ydl, watch_url, ydl_opts

        try:
            with YoutubeDL(ydl_opts(extract_flat=False)) as ydl:
                info = ydl.extract_info(watch_url(track_id), download=False)
            track = track_from_ydl(info)
            return track.thumbnail_url if track is not None else ""
        except Exception:
            logger.debug(
                "SoundCloud thumbnail extract failed: %s",
                track_id,
                exc_info=True,
            )
            return ""

    @staticmethod
    def sync_download(opts: dict, url: str) -> None:
        from yt_dlp import YoutubeDL

        with YoutubeDL(opts) as ydl:
            ydl.extract_info(url, download=True)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    def shutdown(self) -> None:
        return


class AsyncDownloader(AsyncDownloaderInterface):
    def __init__(self) -> None:
        self._yandex_downloader = AsyncYandexDownloader()
        self._youtube_downloader = AsyncYoutubeDownloader()
        self._soundcloud_downloader = AsyncSoundCloudDownloader()

    async def download_track(self, track: Track) -> None:
        match track.source:
            case TrackSource.YANDEX:
                await self._yandex_downloader.download_track(track)
            case TrackSource.YOUTUBE:
                await self._youtube_downloader.download_track(track)
            case TrackSource.SOUNDCLOUD:
                await self._soundcloud_downloader.download_track(track)

    async def download_cover(self, track: Track) -> None:
        match track.source:
            case TrackSource.YANDEX:
                await self._yandex_downloader.download_cover(track)
            case TrackSource.YOUTUBE:
                await self._youtube_downloader.download_cover(track)
            case TrackSource.SOUNDCLOUD:
                await self._soundcloud_downloader.download_cover(track)

    async def ensure_cover(self, track: Track) -> bool:
        """Скачивает обложку, если файла нет или он обрезан. True если файл целый."""
        PathProvider.ensure_storage_dirs()
        cover_path = Path(self._yandex_downloader.path_provider.get_cover_path(track))
        if cover_file_ok(cover_path):
            return True
        # Локальная обложка: stat/unlink быстрее, чем прыжок в поток
        if cover_path.is_file():  # noqa: ASYNC240
            try:
                cover_path.unlink()  # noqa: ASYNC240
            except OSError:
                logger.debug("Не удалось удалить битую обложку %s", cover_path)
        await self.download_cover(track)
        return cover_file_ok(cover_path)

    async def ensure_covers(self, tracks: list[Track], *, limit: int = 40) -> int:
        """Подгружает обложки для списка треков. Возвращает число скачанных."""
        downloaded = 0
        seen: set[str] = set()
        for track in tracks[: max(0, limit)]:
            key = f"{track.source}:{track.track_id}"
            if key in seen:
                continue
            seen.add(key)
            path = Path(self._yandex_downloader.path_provider.get_cover_path(track))
            if cover_file_ok(path):
                continue
            ok = await self.ensure_cover(track)
            if ok:
                downloaded += 1
        return downloaded

    def shutdown(self) -> None:
        self._youtube_downloader.shutdown()
        self._soundcloud_downloader.shutdown()

    async def close(self) -> None:
        await self._youtube_downloader.close()
        await self._soundcloud_downloader.close()
