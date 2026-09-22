"""Локальный HTTP-прокси для Qt: играет URL сразу, Range-reconnect к CDN.

Qt FFmpeg на прямом Yandex HTTP заполняет ~1.4 МБ, перестаёт читать,
CDN рвёт idle-сокет (~35 с), Qt зависает на 5–10 с. VLC сам делает
Range-reconnect. Здесь Qt ходит на 127.0.0.1 (сокет не умирает), а к
CDN переподключается прокси. Файл на диск не пишется.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Awaitable, Callable

from aiohttp import ClientSession, ClientTimeout, web
from aiohttp.client_exceptions import ClientConnectionError, ClientPayloadError

from quantis.models import Track

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
_URL_TTL_SEC = 40.0
_CHUNK_BYTES = 64 * 1024
_MAX_RECONNECTS = 8
_CONNECT_TIMEOUT = ClientTimeout(total=15, sock_connect=10)


def _parse_range(header: str | None) -> tuple[int, int | None]:
    """Range: bytes=start-end → (start, end_inclusive|None). Без Range — (0, None)."""
    if not header:
        return 0, None
    match = re.match(r"bytes=(\d+)-(\d+)?", header.strip(), re.I)
    if not match:
        return 0, None
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) is not None else None
    return start, end


def _total_from_content_range(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"/(\d+)\s*$", value)
    return int(match.group(1)) if match else None


def _route_key(track: Track) -> str:
    source = str(track.source).lower()
    safe_id = "".join(
        ch if ch.isalnum() or ch in "-_." else "_" for ch in str(track.track_id)
    )
    return f"{source}/{safe_id}"


class LocalHttpStreamProxy:
    """aiohttp на 127.0.0.1; Range к CDN, без записи файла."""

    def __init__(self, url_fetcher: StreamUrlFetcher) -> None:
        self._url_fetcher = url_fetcher
        self._runner: web.AppRunner | None = None
        self._port = 0
        self._client: ClientSession | None = None
        self._tracks: dict[str, Track] = {}
        self._urls: dict[str, tuple[str, float]] = {}

    @property
    def port(self) -> int:
        return self._port

    def local_url(self, track: Track) -> str:
        return f"http://127.0.0.1:{self._port}/{_route_key(track)}"

    async def ensure_started(self) -> None:
        if self._runner is not None:
            return
        app = web.Application()
        app.router.add_get("/{key:.+}", self._handle)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self._port = int(self._runner.addresses[0][1])
        logger.info("HTTP stream proxy: 127.0.0.1:%s", self._port)

    async def mount(self, track: Track, url: str) -> str:
        await self.ensure_started()
        key = _route_key(track)
        self._tracks[key] = track
        self._urls[key] = (url, time.monotonic())
        return self.local_url(track)

    def invalidate_track(self, track: Track) -> None:
        self._urls.pop(_route_key(track), None)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        self._port = 0
        self._tracks.clear()
        self._urls.clear()

    async def _ensure_client(self) -> ClientSession:
        if self._client is None or self._client.closed:
            self._client = ClientSession(
                headers=_UPSTREAM_HEADERS,
                timeout=ClientTimeout(total=None, sock_connect=10, sock_read=None),
            )
        return self._client

    async def _upstream_url(
        self, key: str, track: Track, *, force: bool = False
    ) -> str | None:
        now = time.monotonic()
        if not force:
            cached = self._urls.get(key)
            if cached is not None and now - cached[1] < _URL_TTL_SEC:
                return cached[0]
        url = await self._url_fetcher(track)
        if not url:
            return None
        self._urls[key] = (url, now)
        return url

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        key = request.match_info["key"]
        track = self._tracks.get(key)
        if track is None:
            raise web.HTTPNotFound()

        start, end = _parse_range(request.headers.get("Range"))
        client = await self._ensure_client()
        url = await self._upstream_url(key, track)
        if not url:
            raise web.HTTPBadGateway(text="no upstream url")

        if request.method == "HEAD":
            return await self._head(client, key, track, url, start, end)

        return await self._stream(request, client, key, track, start, end)

    async def _head(
        self,
        client: ClientSession,
        key: str,
        track: Track,
        url: str,
        start: int,
        end: int | None,
    ) -> web.Response:
        range_end = str(start if end is None else end)
        headers = {"Range": f"bytes={start}-{range_end}"}
        for attempt in range(2):
            async with client.get(
                url, headers=headers, allow_redirects=True, timeout=_CONNECT_TIMEOUT
            ) as upstream:
                if upstream.status in (403, 410) and attempt == 0:
                    refreshed = await self._upstream_url(key, track, force=True)
                    if not refreshed:
                        raise web.HTTPBadGateway()
                    url = refreshed
                    continue
                if upstream.status >= 400:
                    raise web.HTTPBadGateway(text=f"upstream {upstream.status}")
                http_status, out, _total = self._headers_from_upstream(
                    upstream, start, end
                )
                return web.Response(status=http_status, headers=out)
        raise web.HTTPBadGateway()

    async def _stream(
        self,
        request: web.Request,
        client: ClientSession,
        key: str,
        track: Track,
        start: int,
        end: int | None,
    ) -> web.StreamResponse:
        offset = start
        limit = end + 1 if end is not None else None
        response: web.StreamResponse | None = None
        reconnects = 0
        prepared_total: int | None = None

        while limit is None or offset < limit:
            if request.transport is None or request.transport.is_closing():
                break
            try:
                url = await self._upstream_url(key, track, force=reconnects > 0)
                if not url:
                    break
                range_end = "" if limit is None else str(limit - 1)
                headers = {"Range": f"bytes={offset}-{range_end}"}
                async with client.get(
                    url, headers=headers, allow_redirects=True
                ) as upstream:
                    if upstream.status in (403, 410):
                        reconnects += 1
                        if reconnects > _MAX_RECONNECTS:
                            break
                        self._urls.pop(key, None)
                        continue
                    if upstream.status == 416:
                        break
                    if upstream.status >= 400:
                        logger.debug(
                            "HTTP proxy upstream %s at %s", upstream.status, offset
                        )
                        break
                    if upstream.status != 206 and offset > 0:
                        logger.warning("HTTP proxy: CDN ignored Range @%s", offset)
                        break

                    if response is None:
                        http_status, out, total = self._headers_from_upstream(
                            upstream, start, end
                        )
                        prepared_total = total
                        if limit is None and total is not None:
                            limit = total
                        response = web.StreamResponse(status=http_status, headers=out)
                        await response.prepare(request)

                    async for chunk in upstream.content.iter_chunked(_CHUNK_BYTES):
                        if not chunk:
                            break
                        if limit is not None:
                            remain = limit - offset
                            if remain <= 0:
                                await response.write_eof()
                                return response
                            if len(chunk) > remain:
                                chunk = chunk[:remain]
                        await response.write(chunk)
                        offset += len(chunk)
                        if limit is not None and offset >= limit:
                            await response.write_eof()
                            return response
                if limit is None:
                    break
                if prepared_total is not None and offset >= prepared_total:
                    break
            except (
                ClientPayloadError,
                ClientConnectionError,
                ConnectionResetError,
            ) as exc:
                reconnects += 1
                if reconnects > _MAX_RECONNECTS:
                    logger.warning("HTTP proxy: исчерпаны reconnect @%s", offset)
                    break
                logger.debug("HTTP proxy reconnect @%s: %s", offset, exc)
                self._urls.pop(key, None)
                continue
            except Exception:
                logger.debug("HTTP proxy pipe error @%s", offset, exc_info=True)
                break

        if response is None:
            raise web.HTTPBadGateway(text="upstream failed")
        try:
            await response.write_eof()
        except Exception:
            logger.debug("HTTP proxy write_eof failed", exc_info=True)
        return response

    @staticmethod
    def _headers_from_upstream(
        upstream: object, start: int, end: int | None
    ) -> tuple[int, dict[str, str], int | None]:
        raw = getattr(upstream, "headers", {})
        status = int(getattr(upstream, "status", 200))
        total = _total_from_content_range(raw.get("Content-Range"))
        if total is None and raw.get("Content-Length"):
            length = int(raw["Content-Length"])
            total = start + length if status == 206 else length

        last = end
        if total is not None:
            last = total - 1 if end is None else min(end, total - 1)

        out = {
            "Accept-Ranges": "bytes",
            "Content-Type": str(raw.get("Content-Type") or "audio/mpeg"),
            "Cache-Control": "no-store",
        }
        http_status = 200
        ranged = start > 0 or end is not None
        if ranged and total is not None and last is not None:
            http_status = 206
            out["Content-Range"] = f"bytes {start}-{last}/{total}"
        if last is not None:
            out["Content-Length"] = str(last - start + 1)
        return http_status, out, total
