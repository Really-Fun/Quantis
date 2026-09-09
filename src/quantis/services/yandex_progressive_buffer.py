"""Прогрессивный буфер потока: фоновая запись в temp, воспроизведение сразу.

Для Qt Multimedia Yandex/SoundCloud MP3 range-загрузка в локальный файл
стабильнее прямого HTTP: CDN-URL короткоживущие. VLC играет эти ссылки
напрямую. YouTube так буферить нельзя — неполный MP4/m4a не открывается
(moov/CTTS), часовые ролики ломаются. HLS (SoundCloud) тоже не буферим.

Файл сразу растягивается до полного размера, поэтому Qt с первой секунды
знает настоящую длительность и умеет перематывать в любую точку. Скачивание
идёт диапазонами: при перемотке голова прыгает к нужному смещению, а пропуски
дозакачиваются после того, как хвост дойдёт до конца.
"""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientConnectionError, ClientPayloadError

from quantis.models import Track, TrackSource

logger = logging.getLogger(__name__)

StreamUrlFetcher = Callable[[Track], Awaitable[str | None]]

_UPSTREAM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
}
_URL_TTL_SEC = 45.0
_SEGMENT_BYTES = 1024 * 1024
_CHUNK_BYTES = 32 * 1024
_MAX_SEGMENT_RETRIES = 5
# ~6с CBR 320kbps. 96КБ хватало на «пчик» и ложный EndOfMedia по нулевому хвосту.
_MIN_START_BYTES = 256 * 1024
_RECOVERY_EXTRA_BYTES = 256 * 1024
_RECOVERY_WAIT_SEC = 8.0
_AHEAD_BYTES = 2 * 1024 * 1024
_ECO_AHEAD_BYTES = 4 * 1024 * 1024
_START_TIMEOUT_SEC = 25.0
_BYTES_PER_SEC_EST = 40_000
# ID3-теги и погрешность CBR-оценки: качаем с запасом до точки перемотки.
_SEEK_LEAD_BYTES = 64 * 1024
_SEEK_READY_BYTES = 192 * 1024
_SEEK_WAIT_SEC = 6.0
_SEEK_POLL_SEC = 0.05


def _total_from_content_range(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"/(\d+)\s*$", value)
    return int(match.group(1)) if match else None


def _buffer_path(track: Track, root: Path) -> Path:
    source = str(track.source).lower()
    ext = "m4a" if source == TrackSource.YOUTUBE else "mp3"
    safe_id = "".join(
        ch if ch.isalnum() or ch in "-_." else "_" for ch in str(track.track_id)
    )
    return root / f"{source}_{safe_id}.{ext}"


def _track_key(track: Track) -> str:
    return f"{track.source}:{track.track_id}"


class ProgressiveStreamBuffer:
    """Один активный temp-файл; сегментная загрузка с CDN."""

    def __init__(self, url_fetcher: StreamUrlFetcher) -> None:
        self._url_fetcher = url_fetcher
        self._dir = Path(tempfile.gettempdir()) / "quantis_stream"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._client: ClientSession | None = None
        self._upstream: dict[str, tuple[str, float]] = {}
        self._task: asyncio.Task[None] | None = None
        self._path: Path | None = None
        self._ready = asyncio.Event()
        self._wake = asyncio.Event()
        self._lock = asyncio.Lock()
        self._eco = False

        self._track_key: str | None = None
        self._duration_ms = 0
        self._total: int | None = None
        self._ranges: list[tuple[int, int]] = []
        self._seek_offset: int | None = None
        self._play_offset = 0
        self._failed = False

    def set_eco(self, enabled: bool) -> None:
        self._eco = enabled

    def invalidate_track(self, track: Track) -> None:
        self._upstream.pop(str(track.track_id), None)

    async def _ensure_client(self) -> ClientSession:
        if self._client is None:
            self._client = ClientSession(headers=_UPSTREAM_HEADERS)
        return self._client

    async def close(self) -> None:
        await self.cancel()
        if self._client is not None:
            await self._client.close()
            self._client = None
        self._upstream.clear()

    async def cancel(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("Stream buffer: задача с ошибкой", exc_info=True)
        path = self._path
        self._path = None
        self._track_key = None
        self._ranges = []
        self._total = None
        self._seek_offset = None
        self._play_offset = 0
        self._failed = False
        self._ready = asyncio.Event()
        self._wake = asyncio.Event()
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Не удалось удалить temp %s", path, exc_info=True)

    async def open(self, track: Track, *, url: str | None = None) -> str | None:
        """Старт фоновой загрузки; возвращает путь, когда буфер готов к play."""
        key = _track_key(track)
        path = _buffer_path(track, self._dir)

        async with self._lock:
            if self._is_reusable(key, path):
                logger.debug("Stream buffer: переиспользуем «%s»", track.title)
                return str(path)
            await self.cancel()
            self._track_key = key
            self._path = path
            self._duration_ms = max(0, int(getattr(track, "duration_ms", 0) or 0))
            self._upstream.pop(str(track.track_id), None)
            if url:
                self._upstream[str(track.track_id)] = (url, time.monotonic())
            self._task = asyncio.create_task(self._download(track, path))

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=_START_TIMEOUT_SEC)
        except TimeoutError:
            logger.warning("Stream buffer: таймаут старта «%s»", track.title)
            await self.cancel()
            return None

        if self._failed or self._prefix_bytes() <= 0:
            await self.cancel()
            return None

        return str(path)

    def _is_reusable(self, key: str, path: Path) -> bool:
        """Тот же трек уже качается/скачан — не начинаем заново с нуля.

        Иначе восстановление потока после перемотки стирало бы прогресс
        и уводило воспроизведение в бесконечный цикл перезапусков.
        """
        if self._track_key != key or self._path != path or self._failed:
            return False
        if not self._ready.is_set() or not path.is_file():
            return False
        task = self._task
        if task is not None and task.done() and task.exception() is not None:
            return False
        return self._prefix_bytes() > 0

    def owns(self, source: str | None) -> bool:
        """Играет ли плеер именно этот temp-файл."""
        if not source or self._path is None:
            return False
        try:
            return Path(source) == self._path
        except (TypeError, ValueError):
            return False

    def report_position_ms(self, track: Track, position_ms: int) -> None:
        """Держит загрузку впереди реальной позиции плеера, а не начала файла."""
        if self._track_key != _track_key(track):
            return
        offset = self._offset_for_ms(position_ms)
        if offset is None:
            return
        self._play_offset = offset
        ahead = _ECO_AHEAD_BYTES if self._eco else _AHEAD_BYTES
        if self._contiguous_end(offset) - offset < ahead // 2:
            self._wake.set()

    async def wait_for_more_prefix(
        self,
        track: Track,
        *,
        extra_bytes: int = _RECOVERY_EXTRA_BYTES,
        timeout: float = _RECOVERY_WAIT_SEC,
    ) -> bool:
        """Ждёт ещё префикс после раннего EOF, не переигрывая те же 2 секунды."""
        if self._track_key != _track_key(track):
            return True
        target = self._prefix_bytes() + max(0, int(extra_bytes))
        if self._total:
            target = min(target, self._total)
        self._wake.set()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._failed:
                return False
            if self._prefix_bytes() >= target:
                return True
            await asyncio.sleep(_SEEK_POLL_SEC)
        return self._prefix_bytes() >= target

    async def seek_to_ms(self, track: Track, position_ms: int) -> bool:
        """Уводит голову загрузки к точке перемотки и ждёт первые байты.

        Без ожидания Qt прочитал бы ещё не скачанный (нулевой) хвост файла и
        принял его за конец трека — отсюда «перемотал вперёд, и всё встало».
        """
        if self._track_key != _track_key(track):
            return True
        offset = self._offset_for_ms(position_ms)
        if offset is None:
            return True
        self._play_offset = offset
        if self._is_downloaded(offset, offset + _SEEK_READY_BYTES):
            return True

        self._seek_offset = offset
        self._wake.set()
        deadline = time.monotonic() + _SEEK_WAIT_SEC
        while time.monotonic() < deadline:
            task = self._task
            if self._failed or task is None or task.done():
                return self._is_downloaded(offset, offset + _SEEK_READY_BYTES)
            if self._is_downloaded(offset, offset + _SEEK_READY_BYTES):
                return True
            await asyncio.sleep(_SEEK_POLL_SEC)
        logger.debug("Stream buffer: перемотка @%dms не дождалась данных", position_ms)
        return False

    def _offset_for_ms(self, position_ms: int) -> int | None:
        total = self._total
        if not total or self._duration_ms <= 0:
            return None
        ratio = max(0.0, min(1.0, position_ms / self._duration_ms))
        return max(0, min(int(total * ratio) - _SEEK_LEAD_BYTES, total - 1))

    # --- карта скачанных диапазонов -------------------------------------

    def _mark(self, start: int, end: int) -> None:
        if end <= start:
            return
        ordered = sorted([*self._ranges, (start, end)])
        merged = [ordered[0]]
        for begin, finish in ordered[1:]:
            last_begin, last_end = merged[-1]
            if begin <= last_end:
                merged[-1] = (last_begin, max(last_end, finish))
            else:
                merged.append((begin, finish))
        self._ranges = merged

    def _prefix_bytes(self) -> int:
        if not self._ranges:
            return 0
        start, end = self._ranges[0]
        return end if start == 0 else 0

    def _is_downloaded(self, start: int, end: int) -> bool:
        limit = min(end, self._total) if self._total else end
        return any(begin <= start and finish >= limit for begin, finish in self._ranges)

    def _first_gap(self) -> int | None:
        total = self._total
        if total is None:
            return 0
        position = 0
        for start, end in self._ranges:
            if start > position:
                return position
            position = max(position, end)
        return position if position < total else None

    def _contiguous_end(self, offset: int) -> int:
        position = max(0, offset)
        for start, end in self._ranges:
            if end <= position:
                continue
            if start > position:
                return position
            position = end
        return position

    def _next_offset(self, offset: int) -> int | None:
        total = self._total
        if total is not None and offset >= total:
            return self._first_gap()
        position = self._contiguous_end(offset)
        if total is not None and position >= total:
            return self._first_gap()
        return position

    # --- загрузка --------------------------------------------------------

    async def _upstream_url(self, track: Track, *, force: bool = False) -> str | None:
        key = str(track.track_id)
        now = time.monotonic()
        if not force:
            cached = self._upstream.get(key)
            if cached is not None and now - cached[1] < _URL_TTL_SEC:
                return cached[0]
        else:
            self._upstream.pop(key, None)

        url = await self._url_fetcher(track)
        if not url:
            return None
        self._upstream[key] = (url, now)
        return url

    def _invalidate(self, track_id: str) -> None:
        self._upstream.pop(track_id, None)

    def _preallocate(self, handle, total: int) -> None:
        """Полный размер файла сразу: Qt видит верную длительность и seek."""
        try:
            handle.truncate(total)
        except OSError:
            logger.debug("Не удалось растянуть temp до %s байт", total, exc_info=True)

    def _apply_total(self, handle, total: int | None) -> None:
        if total is None or self._total is not None:
            return
        self._total = total
        self._preallocate(handle, total)

    def _maybe_ready(self, handle=None) -> None:
        if self._ready.is_set():
            return
        prefix = self._prefix_bytes()
        if prefix >= _MIN_START_BYTES:
            if handle is not None:
                handle.flush()
            self._ready.set()
        elif self._total is not None and prefix >= self._total:
            if handle is not None:
                handle.flush()
            self._ready.set()

    async def _fetch_into(
        self,
        client: ClientSession,
        track: Track,
        track_id: str,
        handle,
        offset: int,
    ) -> int:
        """Пишет диапазон в файл кусками; ready взводится по ходу дела."""
        written = 0
        for attempt in range(_MAX_SEGMENT_RETRIES):
            start = offset + written
            end = offset + _SEGMENT_BYTES - 1
            if self._total is not None:
                end = min(end, self._total - 1)
            if end < start:
                return written

            try:
                url = await self._upstream_url(track, force=attempt > 0)
                if not url:
                    raise RuntimeError("no upstream url")

                headers = {"Range": f"bytes={start}-{end}"}
                async with client.get(
                    url, headers=headers, allow_redirects=True
                ) as upstream:
                    if upstream.status in (403, 410):
                        self._invalidate(track_id)
                        continue
                    if upstream.status == 416:
                        return written
                    if upstream.status >= 400:
                        text = await upstream.text()
                        raise RuntimeError(
                            f"upstream {upstream.status}: {text[:200]}"
                        )
                    if upstream.status != 206 and start > 0:
                        # CDN проигнорировал Range — дописывать нельзя, иначе
                        # файл склеится из кусков не с тех позиций.
                        raise RuntimeError("upstream ignores Range requests")

                    total = _total_from_content_range(
                        upstream.headers.get("Content-Range")
                    )
                    if total is None and upstream.headers.get("Content-Length"):
                        length = int(upstream.headers["Content-Length"])
                        total = start + length if upstream.status == 206 else length
                    self._apply_total(handle, total)

                    handle.seek(start)
                    async for chunk in upstream.content.iter_chunked(_CHUNK_BYTES):
                        handle.write(chunk)
                        written += len(chunk)
                        self._mark(offset, offset + written)
                        self._maybe_ready(handle)
                        if self._seek_offset is not None:
                            handle.flush()
                            return written
                    handle.flush()
                    return written
            except (ClientPayloadError, ClientConnectionError) as exc:
                logger.debug(
                    "Stream buffer segment retry %s@%s: %s", track_id, start, exc
                )
                self._invalidate(track_id)
                continue

        if written > 0:
            return written
        raise RuntimeError("upstream segment failed")

    async def _pace(self, offset: int) -> None:
        """Держим запас впереди точки прослушивания, а не грузим на полной."""
        if self._seek_offset is not None:
            return
        ahead_target = _ECO_AHEAD_BYTES if self._eco else _AHEAD_BYTES
        if offset - self._play_offset < ahead_target:
            return
        factor = 1.8 if self._eco else 2.2
        delay = _SEGMENT_BYTES / (_BYTES_PER_SEC_EST * factor)
        if self._eco:
            delay = min(delay, 8.0)
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=delay)
        except TimeoutError:
            pass

    async def _download(self, track: Track, path: Path) -> None:
        track_id = str(track.track_id)
        client = await self._ensure_client()
        offset = 0

        try:
            with path.open("wb+") as handle:
                while True:
                    requested = self._seek_offset
                    if requested is not None:
                        self._seek_offset = None
                        offset = requested

                    target = self._next_offset(offset)
                    if target is None:
                        break
                    offset = target

                    written = await self._fetch_into(
                        client, track, track_id, handle, offset
                    )
                    if written <= 0:
                        if self._total is None:
                            break
                        # 416/пустой ответ — считаем хвост закрытым.
                        self._mark(offset, self._total)
                        if self._first_gap() is None:
                            break
                        continue

                    offset += written
                    self._maybe_ready(handle)
                    if self._first_gap() is None:
                        break
                    await self._pace(offset)

                handle.flush()

            if self._prefix_bytes() <= 0:
                raise RuntimeError("пустой поток")

            logger.debug(
                "Stream buffer готов «%s»: %s/%s bytes → %s",
                track.title,
                self._prefix_bytes(),
                self._total,
                path.name,
            )
            self._ready.set()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Stream buffer: ошибка «%s»", track.title)
            self._failed = True
            self._ready.set()
            raise

    def cleanup_old_files(self, keep: Path | None = None) -> None:
        keep_resolved = keep.resolve() if keep is not None and keep.exists() else None
        for path in self._dir.glob("*_*.*"):
            try:
                if keep_resolved is not None and path.resolve() == keep_resolved:
                    continue
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("Не удалось удалить temp %s", path, exc_info=True)


# Обратная совместимость
YandexProgressiveBuffer = ProgressiveStreamBuffer
