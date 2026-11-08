"""Асинхронное скачивание (треков, обложек)
Наследуется абстрактный класс
Yandex
Youtube"""

import asyncio
import logging
import random
from abc import ABC, abstractmethod
from asyncio import Semaphore, get_running_loop
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Protocol

import aiofiles
import aiohttp

from quantis.config import Clients
from quantis.models.track import (
    SoundCloudTrack,
    Track,
    TrackSource,
    YandexTrack,
    YoutubeTrack,
    strip_youtube_stats,
)
from quantis.providers import PathProvider
from quantis.services.cover_validate import cover_bytes_ok, cover_file_ok
from quantis.services.track_tags import (
    TrackMeta,
    read_identity,
    source_url,
    write_tags,
)
from quantis.services.wallpaper_policy import (
    wallpaper_cache_format,
    wallpaper_duration_filter,
)
from quantis.services.yandex_streamer import _RATE_LIMIT_RETRIES, _is_rate_limited

if TYPE_CHECKING:
    from quantis.providers.library_index import LibraryIndex

logger = logging.getLogger(__name__)

_AUDIO_FORMAT = (
    "ba[ext=m4a]/ba[ext=mp3]/"
    "bestaudio[ext=m4a]/bestaudio[ext=mp3]/"
    "bestaudio[protocol=https]/bestaudio"
)
_VIDEO_FORMAT = wallpaper_cache_format(360)
_AUDIO_EXTENSIONS = frozenset({"m4a", "mp3"})
_MAX_COVER_BYTES = 8 * 1024 * 1024


@dataclass
class DownloadedAudio:
    """Скачанный файл и метаданные трека."""

    path: Path
    meta: TrackMeta


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _base_meta(track: Track) -> TrackMeta:
    source = str(track.source).lower()
    track_id = str(track.track_id)
    if source == "soundcloud":
        # Ленивый импорт: циклическая зависимость providers <-> soundcloud.
        from quantis.services.soundcloud import parse_storage_id

        track_id = parse_storage_id(track_id) or track_id
    return TrackMeta(
        source=source,
        track_id=track_id,
        title=track.title,
        artist=track.author,
        source_url=source_url(source, track_id),
    )


def _apply_service_names(
    meta: TrackMeta, title: str, artist: str, *, prefer_service: bool
) -> None:
    """Название/исполнитель сервиса (миграция) или трека Quantis (скачивание).

    Пустое значение одной стороны заменяется значением другой.
    """
    own_title, own_artist = _text(meta.title), _text(meta.artist)
    if prefer_service:
        meta.service_title = title
        meta.title = title or own_title
        meta.artist = artist or own_artist
    else:
        meta.title = meta.title or title
        meta.artist = meta.artist or artist


def _legacy_or_service(own: str, service: str) -> str:
    """Имя из старого файла, если сервис не дал чистого названия трека.

    Старое имя заменило ``? / :`` и т. п. на ``_``: если значение сервиса после
    той же замены совпадает с ним, берём версию сервиса с настоящими символами.
    """
    from quantis.providers.path_provider import PathProvider

    if not own or not service:
        return own or service
    sanitized = PathProvider._sanitize_filename_part(service)
    return service if sanitized.casefold() == own.casefold() else own


def _year_from_date(value: Any) -> int | None:
    if isinstance(value, str) and len(value) >= 4:
        return _int_or_none(value[:4])
    return None


def meta_from_yandex(
    track: Track, ya_track: Any, *, prefer_service: bool = False
) -> TrackMeta:
    """Метаданные из объекта трека yandex-music (любое поле может быть None).

    prefer_service=True (миграция старых файлов): название и исполнители берутся
    из ответа сервиса, имя файла было искажено санитизацией.
    """
    meta = _base_meta(track)
    artists = [
        _text(getattr(artist, "name", None))
        for artist in (getattr(ya_track, "artists", None) or [])
    ]
    _apply_service_names(
        meta,
        _text(getattr(ya_track, "title", None)),
        ", ".join(name for name in artists if name),
        prefer_service=prefer_service,
    )
    albums = getattr(ya_track, "albums", None)
    if not albums:
        return meta
    album = albums[0]
    meta.album = _text(getattr(album, "title", None))
    meta.year = _int_or_none(getattr(album, "year", None))
    meta.genre = _text(getattr(album, "genre", None))
    position = getattr(album, "track_position", None)
    meta.track_number = _int_or_none(getattr(position, "index", None))
    names = [
        _text(getattr(artist, "name", None))
        for artist in (getattr(album, "artists", None) or [])
    ]
    meta.album_artist = ", ".join(name for name in names if name)
    return meta


def meta_from_ydl(
    track: Track, info: dict, *, prefer_service: bool = False
) -> TrackMeta:
    """Метаданные из ответа yt-dlp (prefer_service — см. meta_from_yandex)."""
    meta = _base_meta(track)
    own_title, own_artist = _text(meta.title), _text(meta.artist)
    track_name = _text(info.get("track"))
    named_artist = _text(info.get("artist"))
    title = track_name or _text(info.get("title"))
    artist = named_artist or _text(info.get("uploader"))
    if artist and meta.source == "youtube":
        artist = strip_youtube_stats(artist)
    _apply_service_names(meta, title, artist, prefer_service=prefer_service)
    if prefer_service and meta.source == "youtube":
        # Заголовок и канал обычного ролика — не название трека и исполнитель
        # («X - Song (Official Video)»): без полей YouTube Music берём имя файла.
        if not track_name:
            meta.title = _legacy_or_service(own_title, title)
        if not named_artist:
            meta.artist = _legacy_or_service(own_artist, artist)
    meta.album = _text(info.get("album"))
    meta.genre = _text(info.get("genre"))
    meta.track_number = _int_or_none(info.get("track_number"))
    year = _int_or_none(info.get("release_year"))
    if year is None:
        year = _year_from_date(info.get("release_date"))
    if year is None:
        year = _year_from_date(info.get("upload_date"))
    meta.year = year
    return meta


# Ошибки yt-dlp, означающие «такого трека нет», а не сбой сети/лимит.
_YDL_NOT_FOUND = (
    "video unavailable",
    "private video",
    "this video has been removed",
    "this video does not exist",
    "http error 404",
)
_YDL_TRANSIENT = ("try again later", "sign in to confirm")


def _ydl_not_found(exc: BaseException) -> bool:
    text = str(exc).casefold()
    if any(marker in text for marker in _YDL_TRANSIENT):
        return False
    return any(marker in text for marker in _YDL_NOT_FOUND)


_YDL_NETWORK = (
    "got error",
    "ssl",
    "eof occurred",
    "timed out",
    "connection reset",
    "connection aborted",
    "remote end closed",
    "incompleteread",
    "temporary failure in name resolution",
)
"""Обрыв сети посреди загрузки: та же попытка обычно проходит со второго раза."""
_YDL_NETWORK_RETRY_DELAY = 2.0


def _ydl_network_error(exc: BaseException) -> bool:
    text = str(exc).casefold()
    return any(marker in text for marker in _YDL_NETWORK)


def _ydl_http_retry_sleep(attempt: int) -> float:
    """Пауза yt-dlp перед повтором куска: 1, 2, 4, 4… с."""
    return float(min(2**attempt, 4))


async def _backoff_sleep(delay: float) -> None:
    """Пауза перед повтором при лимите Яндекса (в тестах подменяется)."""
    await asyncio.sleep(delay)


def _downloaded_from_info(track: Track, info: Any) -> DownloadedAudio | None:
    """Путь файла берём из ответа yt-dlp; суффикс должен быть аудио."""
    try:
        filepath = info["requested_downloads"][0]["filepath"]
    except (KeyError, IndexError, TypeError):
        return None
    if not filepath:
        return None
    path = Path(filepath)
    ext = path.suffix.lstrip(".").lower()
    if ext not in _AUDIO_EXTENSIONS:
        return None
    if isinstance(track, (YoutubeTrack, SoundCloudTrack)):
        track.extension = ext
    return DownloadedAudio(path=path, meta=meta_from_ydl(track, info))


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


ProgressCallback = Callable[[Track, "float | None"], None]
"""``(track, доля 0..1)``; None — сколько осталось, неизвестно."""


def _ydl_progress_hook(
    track: Track, report: ProgressCallback
) -> Callable[[dict], None]:
    """progress_hooks для yt-dlp: доля скачанного звука."""

    def hook(status: dict) -> None:
        if status.get("status") != "downloading":
            return
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        done = status.get("downloaded_bytes")
        if total and done is not None:
            report(track, min(1.0, done / total))
        else:
            report(track, None)

    return hook


class AsyncDownloaderInterface(ABC):
    """Абстрактный класс для Downloader'ов"""

    on_progress: ProgressCallback | None = None
    """Ставит AsyncDownloader: прогресс скачивания звука. Может вызываться
    из потока пула (yt-dlp)."""

    def _report_progress(self, track: Track, fraction: float | None) -> None:
        if self.on_progress is not None:
            self.on_progress(track, fraction)

    @abstractmethod
    async def download_track(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> DownloadedAudio | None: ...

    @abstractmethod
    async def lookup_meta(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> TrackMeta | None:
        """Метаданные сервиса для миграции.

        None — сервис чисто ответил «нет такого трека» или клиента нет;
        сбой сети, лимит и прочие ошибки бросаются.
        """

    async def fetch_meta(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> TrackMeta | None:
        """lookup_meta, который не бросает: None при любой ошибке."""
        try:
            return await self.lookup_meta(track)
        except Exception:
            logger.debug("Метаданные недоступны: %s", track, exc_info=True)
            return None

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

    async def lookup_meta(self, track: Track | YandexTrack | YoutubeTrack):
        """Метаданные без скачивания; лимит 429 повторяется с паузами."""
        from yandex_music.exceptions import NotFoundError

        client = self.client
        if client is None:
            return None
        track_id = int(track.track_id)
        for delay in (*_RATE_LIMIT_RETRIES, None):
            try:
                track_info = await client.tracks(track_id)
            except NotFoundError:
                return None
            except Exception as exc:
                if delay is None or not _is_rate_limited(exc):
                    raise
                logger.info(
                    "Яндекс: лимит запросов для «%s», повтор через %.1f с",
                    track.title,
                    delay,
                )
                await _backoff_sleep(delay * random.uniform(0.8, 1.3))
                continue
            if not track_info:
                return None
            return meta_from_yandex(track, track_info[0], prefer_service=True)
        return None  # недостижимо: последняя попытка либо вернула, либо бросила

    async def download_track(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> DownloadedAudio | None:
        """Скачивает трек с яндекса. Асинхронное скачивание

        Args:
            track (YandexTrack): Трек с Яндекса
        """
        if self.client is None:
            logger.warning(
                "Клиент ЯндексМузыки не инициализирован.Невозможно скачать трек: %s",
                track,
            )
            return None
        try:
            PathProvider.ensure_storage_dirs()
            track_info = await self.client.tracks(int(track.track_id))
            current_track = track_info[0]
            file_path = self.path_provider.get_track_path(track)

            is_authorized = bool(getattr(self.client, "token", None))
            # Полный битрейт — не preview
            bitrate = 320 if is_authorized else 192
            if not await self._download_with_progress(
                track, current_track, file_path, bitrate
            ):
                self._report_progress(track, None)
                await current_track.download_async(file_path, bitrate_in_kbps=bitrate)
            return DownloadedAudio(
                path=Path(file_path), meta=meta_from_yandex(track, current_track)
            )
        except Exception:
            logger.exception("Не удалось скачать трек с Яндекс.Музыки: %s", track)
            return None

    async def _download_with_progress(
        self, track: Track, yandex_track, file_path: str, bitrate: int
    ) -> bool:
        """Файл по прямой ссылке кусками — с прогрессом. False — не вышло
        (тогда качаем библиотекой целиком, без процентов)."""
        dest = Path(file_path)
        part = dest.with_name(dest.name + ".part")
        try:
            info = await yandex_track.get_specific_download_info_async("mp3", bitrate)
            if info is None:
                return False
            link = await info.get_direct_link_async()
            proxy = getattr(getattr(self.client, "request", None), "proxy_url", None)
            timeout = aiohttp.ClientTimeout(total=None, sock_read=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(link, proxy=proxy) as response:
                    response.raise_for_status()
                    total = response.content_length or 0
                    done = 0
                    self._report_progress(track, 0.0 if total else None)
                    async with aiofiles.open(part, "wb") as file:
                        async for chunk in response.content.iter_chunked(64 * 1024):
                            await file.write(chunk)
                            done += len(chunk)
                            if total:
                                self._report_progress(track, min(1.0, done / total))
            if total and done < total:
                raise OSError(f"оборвалось на {done} из {total} байт")
            part.replace(dest)
            return True
        except Exception:
            logger.info(
                "Яндекс: загрузка с прогрессом не удалась, качаем целиком: %s",
                track,
                exc_info=True,
            )
            part.unlink(missing_ok=True)
            return False

    async def download_cover(self, track: Track | YandexTrack | YoutubeTrack) -> None:
        """Скачивает обложку трека с платформы Яндекс. Асинхронное скачивание

        Args:
            track (YandexTrack): Трек с Яндекса
        """
        if self.client is None:
            logger.warning(
                "Клиент ЯндексМузыки не инициализирован.Невозможно скачать трек: %s",
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
            # googlevideo рвёт длинные открытые запросы (SSL EOF посреди файла):
            # качаем кусками по 10 МБ и повторяем оборвавшийся кусок с паузой.
            "http_chunk_size": 10 * 1024 * 1024,
            "retries": 5,
            "retry_sleep_functions": {"http": _ydl_http_retry_sleep},
        }
        self.path_provider = PathProvider()
        from quantis.core.worker_pool import get_worker_pool

        self._executor = get_worker_pool()
        self._owns_executor = False
        self._session: Optional[aiohttp.ClientSession] = None
        self._semaphore = Semaphore(value=8)

    def _attempt_opts(self, outtmpl: str, *, video: bool = False) -> list[dict]:
        """Порядок попыток как у стримера: клиенты yt-dlp по умолчанию без
        cookies (сейчас только они стабильно отдают itag 140), потом android,
        потом cookies. Один android часто отвечает SABR без ссылок, а с
        cookies yt-dlp берёт web-клиенты, которым нужен JS-решатель."""
        return [
            self._ydl_opts_default(outtmpl, video=video),
            self._ydl_opts(outtmpl, video=video),
            self._ydl_opts_fallback(outtmpl, video=video),
        ]

    def _ydl_opts_default(self, outtmpl: str, *, video: bool = False) -> dict:
        opts = {
            **self._base_opts,
            "outtmpl": outtmpl,
            "format": self._video_format() if video else _AUDIO_FORMAT,
        }
        if video:
            opts["match_filter"] = wallpaper_duration_filter
        return opts

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

    async def _download_audio(
        self, track: Track | YoutubeTrack
    ) -> DownloadedAudio | None:
        outtmpl = self._audio_outtmpl(track)
        errors: list[str] = []
        hook = _ydl_progress_hook(track, self._report_progress)
        for opts in self._attempt_opts(outtmpl, video=False):
            opts = {**opts, "progress_hooks": [hook]}
            for retry in (True, False):
                try:
                    info = await get_running_loop().run_in_executor(
                        self._executor, self.sync_download, opts, track.track_id
                    )
                    return _downloaded_from_info(track, info)
                except Exception as exc:
                    errors.append(f"{type(exc).__name__}: {exc}")
                    logger.debug(
                        "YouTube audio download attempt failed for %s",
                        track.track_id,
                        exc_info=True,
                    )
                    if not (retry and _ydl_network_error(exc)):
                        break
                    # Формат нашёлся, оборвалась сеть: эта попытка верная —
                    # повторяем её (докачает .part), а не берём заведомо худшие.
                    logger.info(
                        "YouTube %s: обрыв сети, повтор загрузки", track.track_id
                    )
                    await _backoff_sleep(_YDL_NETWORK_RETRY_DELAY)
        logger.warning(
            "YouTube %s: все попытки скачать звук не удались:\n  %s",
            track.track_id,
            "\n  ".join(errors),
        )
        return None

    async def lookup_meta(self, track: Track | YandexTrack | YoutubeTrack):
        """Метаданные без скачивания. None — видео нет; иные сбои бросаются."""
        outtmpl = self._audio_outtmpl(track)
        error: Exception | None = None
        for opts in self._attempt_opts(outtmpl, video=False):
            try:
                info = await get_running_loop().run_in_executor(
                    self._executor, self.sync_extract, opts, track.track_id
                )
                return meta_from_ydl(track, info, prefer_service=True)
            except Exception as exc:
                logger.debug(
                    "YouTube meta fetch failed for %s", track.track_id, exc_info=True
                )
                if not _ydl_not_found(exc):
                    error = exc
        if error is not None:
            raise error
        return None

    async def _download_video_cache(self, track: Track | YoutubeTrack) -> None:
        outtmpl = self.path_provider.get_video_cache_path(track, extension="%(ext)s")
        for opts in self._attempt_opts(outtmpl, video=True):
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

    async def download_track(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> DownloadedAudio | None:
        """Скачивает аудио (m4a/mp3). MP4 — только в кэш обоев при включённом видеофоне."""
        result = await self._download_audio(track)
        if result is None:
            logger.error("Не удалось скачать трек с YouTube: %s", track.track_id)
            return None
        if self._video_wallpaper_enabled():
            await self._download_video_cache(track)
        return result

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
    def _extract(opts: dict, track_id: int | str, *, download: bool) -> dict:
        from yt_dlp import YoutubeDL

        from quantis.services.url_resolver import is_youtube_video_id

        if not is_youtube_video_id(str(track_id)):
            raise ValueError(f"Некорректный YouTube id: {track_id!r}")

        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(
                f"https://youtube.com/watch?v={track_id}", download=download
            )

    @staticmethod
    def sync_download(opts: dict, track_id: int | str) -> dict:
        return AsyncYoutubeDownloader._extract(opts, track_id, download=True)

    @staticmethod
    def sync_extract(opts: dict, track_id: int | str) -> dict:
        return AsyncYoutubeDownloader._extract(opts, track_id, download=False)

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

    async def lookup_meta(self, track: Track | YandexTrack | YoutubeTrack):
        """Метаданные без скачивания. None — трека нет; иные сбои бросаются."""
        from quantis.services.soundcloud import watch_url

        try:
            info = await get_running_loop().run_in_executor(
                self._executor,
                self.sync_extract,
                self._ydl_opts(self.path_provider.get_track_path(track, "%(ext)s")),
                watch_url(track.track_id),
            )
        except Exception as exc:
            if _ydl_not_found(exc):
                return None
            raise
        return meta_from_ydl(track, info, prefer_service=True)

    async def download_track(
        self, track: Track | YandexTrack | YoutubeTrack
    ) -> DownloadedAudio | None:
        from quantis.services.soundcloud import watch_url

        try:
            outtmpl = self.path_provider.get_track_path(track, extension="%(ext)s")
            PathProvider.ensure_storage_dirs()
            opts = {
                **self._ydl_opts(outtmpl),
                "progress_hooks": [_ydl_progress_hook(track, self._report_progress)],
            }
            info = await get_running_loop().run_in_executor(
                self._executor,
                self.sync_download,
                opts,
                watch_url(track.track_id),
            )
        except Exception:
            logger.exception("Не удалось скачать трек с SoundCloud: %s", track.track_id)
            return None
        result = _downloaded_from_info(track, info)
        if result is None:
            logger.error("Не удалось скачать трек с SoundCloud: %s", track.track_id)
        return result

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
    def sync_download(opts: dict, url: str) -> dict:
        from yt_dlp import YoutubeDL

        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    @staticmethod
    def sync_extract(opts: dict, url: str) -> dict:
        from yt_dlp import YoutubeDL

        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    async def close(self) -> None:
        if self._session is not None and not self._session.closed:
            await self._session.close()
            self._session = None

    def shutdown(self) -> None:
        return


@dataclass(frozen=True)
class TagOutcome:
    """Итог tag_and_rename: путь файла, прошли ли теги проверку, переименован ли."""

    path: Path
    verified: bool
    renamed: bool

    @property
    def complete(self) -> bool:
        return self.verified and self.renamed


class DownloadListener(Protocol):
    """Подписчик на скачивание треков (см. ``AsyncDownloader.add_listener``)."""

    def download_started(self, track: Track) -> None: ...

    def download_progress(self, track: Track, fraction: float | None) -> None: ...

    def download_finished(self, track: Track, ok: bool) -> None: ...


class AsyncDownloader(AsyncDownloaderInterface):
    def __init__(self, index: "LibraryIndex | None" = None) -> None:
        self._index = index
        self._full_tasks: dict[str, asyncio.Future[bool]] = {}
        # Выбор имени и переименование — под одним замком: два разных трека
        # с одинаковым «исполнитель - название» не должны взять одно имя.
        self._rename_lock = asyncio.Lock()
        # Треки, которые сейчас размечает миграция старых файлов: скачивание
        # того же трека ждёт её конца, а миграция пропускает скачиваемые.
        self._retagging: dict[str, asyncio.Event] = {}
        self._yandex_downloader = AsyncYandexDownloader()
        self._youtube_downloader = AsyncYoutubeDownloader()
        self._soundcloud_downloader = AsyncSoundCloudDownloader()
        # Обложку трека на старте просят сразу плеер и палитра: одна загрузка
        # на двоих, иначе лишний запрос каталога упирается в лимит Яндекса.
        self._cover_tasks: dict[str, asyncio.Future[None]] = {}
        self._listeners: list[DownloadListener] = []
        self._last_percent: dict[str, int] = {}
        for source in (
            self._yandex_downloader,
            self._youtube_downloader,
            self._soundcloud_downloader,
        ):
            source.on_progress = self._on_progress

    def add_listener(self, listener: "DownloadListener") -> None:
        """События настоящего скачивания трека (не когда файл уже был).
        Вызываются в потоке asyncio или пула yt-dlp."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def _emit(self, method: str, *args) -> None:
        for listener in list(self._listeners):
            try:
                getattr(listener, method)(*args)
            except Exception:
                logger.exception("Слушатель скачивания упал")

    def _on_progress(self, track: Track, fraction: float | None) -> None:
        # yt-dlp зовёт хук на каждый кусок — наружу не чаще, чем на 1 %.
        key = self._guard_key(str(track.source), str(track.track_id))
        percent = -1 if fraction is None else int(fraction * 100)
        if self._last_percent.get(key) == percent:
            return
        self._last_percent[key] = percent
        self._emit("download_progress", track, fraction)

    def _notify_finished(self, track: Track, ok: bool) -> None:
        self._last_percent.pop(
            self._guard_key(str(track.source), str(track.track_id)), None
        )
        self._emit("download_finished", track, ok)

    def _for(self, track: Track):
        match track.source:
            case TrackSource.YANDEX:
                return self._yandex_downloader
            case TrackSource.YOUTUBE:
                return self._youtube_downloader
            case TrackSource.SOUNDCLOUD:
                return self._soundcloud_downloader
        return None

    async def download_track(self, track: Track) -> DownloadedAudio | None:
        downloader = self._for(track)
        if downloader is None:
            return None
        try:
            return await downloader.download_track(track)
        except Exception:
            logger.exception("Не удалось скачать трек: %s", track)
            return None

    async def lookup_meta(self, track: Track) -> TrackMeta | None:
        """Только для миграции: None — «нет трека»/нет клиента, ошибки бросаются."""
        downloader = self._for(track)
        if downloader is None:
            return None
        return await downloader.lookup_meta(track)

    async def download_cover(self, track: Track) -> None:
        key = f"{track.source}:{track.track_id}"
        task = self._cover_tasks.get(key)
        if task is None:
            task = asyncio.ensure_future(self._download_cover(track))
            self._cover_tasks[key] = task
            task.add_done_callback(lambda _done: self._cover_tasks.pop(key, None))
        await asyncio.shield(task)

    async def _download_cover(self, track: Track) -> None:
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

    @property
    def index(self) -> "LibraryIndex":
        if self._index is not None:
            return self._index
        from quantis.providers.library_index import LibraryIndex

        return LibraryIndex.instance()

    async def download_full(self, track: Track) -> bool:
        """Скачать, положить обложку, записать теги, переименовать, проиндексировать."""
        key = self._guard_key(str(track.source), str(track.track_id))
        task = self._full_tasks.get(key)
        if task is None:
            task = asyncio.ensure_future(self._download_full(track))
            self._full_tasks[key] = task
            task.add_done_callback(lambda _done: self._full_tasks.pop(key, None))
        return await asyncio.shield(task)

    @staticmethod
    def _guard_key(source: str, track_id: str) -> str:
        """Ключ замка: тот же, что у индекса, чтобы замок и индекс не разошлись."""
        from quantis.providers.library_index import track_key

        src, tid = track_key(source, track_id)
        return f"{src}:{tid}"

    def is_downloading(self, source: str, track_id: str) -> bool:
        """Идёт ли download_full для этого трека (id SoundCloud — с `sc` или без)."""
        return self._guard_key(source, track_id) in self._full_tasks

    def begin_retag(self, readings: list[tuple[str, str]]) -> bool:
        """Занимает треки под миграцию. False, если любой из них скачивается."""
        keys = [self._guard_key(s, t) for s, t in readings]
        if any(self.is_downloading(s, t) for s, t in readings):
            return False
        for key in keys:
            self._retagging.setdefault(key, asyncio.Event())
        return True

    def end_retag(self, readings: list[tuple[str, str]]) -> None:
        for s, t in readings:
            event = self._retagging.pop(self._guard_key(s, t), None)
            if event is not None:
                event.set()

    async def _download_full(self, track: Track) -> bool:
        key = self._guard_key(str(track.source), str(track.track_id))
        while (event := self._retagging.get(key)) is not None:
            await event.wait()
        index = self.index
        await index.wait_ready()
        source = str(track.source)
        track_id = str(track.track_id)
        if index.path_for(source, track_id) is not None:
            await self._safe_cover(track)
            track.downloaded = True
            return True
        self._emit("download_started", track)
        try:
            audio = await self.download_track(track)
            if audio is None:
                self._notify_finished(track, False)
                return False
            await self.tag_and_rename(audio.path, audio.meta, track)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._notify_finished(track, False)
            raise
        track.downloaded = True
        self._notify_finished(track, True)
        return True

    async def tag_and_rename(
        self, path: Path, meta: TrackMeta, track: Track
    ) -> TagOutcome:
        """Обложка, теги, проверка, переименование и индекс.

        Если теги не прошли проверку или переименование не удалось, файл
        остаётся под прежним именем, но всё равно попадает в индекс.
        Общая для скачивания и миграции старых файлов: замок имён один.
        """
        path = Path(path)
        cover_ok = await self._safe_cover(track)
        audio = DownloadedAudio(path=path, meta=meta)
        verified = await self._write_and_verify_tags(audio, cover_ok, track)
        index = self.index
        async with self._rename_lock:
            final, renamed = path, False
            if verified:
                final, renamed = await self._rename_human(audio)
            try:
                entry = await asyncio.to_thread(index.put, final)
                if entry is None:
                    logger.warning("Файл не попал в индекс: %s", final)
                elif final != path:
                    await asyncio.to_thread(index.discard, path)
            except Exception:
                logger.warning("Не удалось добавить в индекс: %s", final, exc_info=True)
        return TagOutcome(path=final, verified=verified, renamed=renamed)

    async def _safe_cover(self, track: Track) -> bool:
        """ensure_cover, который не бросает: сбой обложки не ломает скачивание."""
        try:
            return await self.ensure_cover(track)
        except Exception:
            logger.warning("Не удалось получить обложку: %s", track, exc_info=True)
            return False

    async def _write_and_verify_tags(
        self, audio: DownloadedAudio, cover_ok: bool, track: Track
    ) -> bool:
        """Пишет теги и читает их обратно. Любая ошибка даёт False."""
        path = Path(audio.path)
        meta = audio.meta
        try:
            cover = None
            if cover_ok:
                cover = Path(
                    self._yandex_downloader.path_provider.get_cover_path(track)
                )
            await asyncio.to_thread(write_tags, path, meta, cover)
            identity = await asyncio.to_thread(read_identity, path)
        except Exception:
            logger.warning("Не удалось записать теги: %s", path, exc_info=True)
            return False
        if (
            identity is None
            or (identity.source, identity.track_id) != (meta.source, meta.track_id)
            or not identity.title.strip()
        ):
            logger.warning("Теги не прошли проверку, файл не переименован: %s", path)
            return False
        return True

    async def _rename_human(self, audio: DownloadedAudio) -> tuple[Path, bool]:
        """Переименовывает в «Исполнитель - Название». Зовётся под _rename_lock.

        Возвращает (итоговый путь, удалось ли).
        """
        path = Path(audio.path)
        meta = audio.meta
        try:
            target = self._yandex_downloader.path_provider.human_track_path(
                meta.artist,
                meta.title,
                path.suffix.lstrip("."),
                owner=(meta.source, meta.track_id),
            )
            if target == path:
                return target, True
            if await asyncio.to_thread(target.exists):
                # Своя уже размеченная копия (индекс устарел): не перезаписываем.
                try:
                    await asyncio.to_thread(path.unlink)
                except OSError:
                    logger.warning("Не удалось удалить дубликат: %s", path)
                    return path, False
                return target, True
            await asyncio.to_thread(path.replace, target)
            return target, True
        except Exception:
            logger.warning("Не удалось переименовать файл: %s", path, exc_info=True)
            return path, False

    def shutdown(self) -> None:
        self._youtube_downloader.shutdown()
        self._soundcloud_downloader.shutdown()

    async def close(self) -> None:
        await self._youtube_downloader.close()
        await self._soundcloud_downloader.close()
