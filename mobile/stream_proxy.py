"""Локальный HTTP-прокси для YouTube: звук играет сразу, без скачивания.

QMediaPlayer не умеет передавать заголовки запроса, а без нужных (их даёт
yt-dlp) googlevideo не отвечает. Плеер ходит на 127.0.0.1, прокси — к CDN:
с заголовками, кусками по Range (большие сплошные загрузки YouTube режет)
и с переподключением при обрыве. Ссылка протухла (403) — берётся новая.
Файл на диск не пишется. Как в настольном Quantis, только на stdlib.
"""

from __future__ import annotations

import logging
import re
import ssl
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import sources

log = logging.getLogger(__name__)

_CHUNK = 8 * 1024 * 1024  # кусок у CDN
_READ = 64 * 1024  # пишем плееру
_RECONNECTS = 6
_TIMEOUT = 20


def _ssl_context() -> ssl.SSLContext:
    # Сертификаты — как у yt-dlp: certifi.where() (на телефоне — свой certifi.py).
    import certifi

    cafile = certifi.where()
    return ssl.create_default_context(cafile=cafile or None)


def _parse_range(header: str | None) -> tuple[int, int | None]:
    match = re.match(r"bytes=(\d+)-(\d+)?", (header or "").strip(), re.I)
    if not match:
        return 0, None
    return int(match.group(1)), int(match.group(2)) if match.group(2) else None


class _Handler(BaseHTTPRequestHandler):
    server: _Server
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        log.debug("proxy: " + format, *args)

    def do_HEAD(self) -> None:
        self._serve(body=False)

    def do_GET(self) -> None:
        self._serve(body=True)

    def _serve(self, *, body: bool) -> None:
        match = re.fullmatch(r"/yt/([\w-]{6,20})", self.path)
        if not match:
            self.send_error(404)
            return
        video_id = match.group(1)
        try:
            stream = sources.youtube_stream(video_id)
            total = stream.size or self.server.probe_size(video_id)
        except Exception as exc:
            log.warning("proxy: нет ссылки на %s: %s", video_id, exc)
            self.send_error(502)
            return
        start, end = _parse_range(self.headers.get("Range"))
        last = total - 1 if end is None else min(end, total - 1)
        if start > last:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{total}")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        partial = self.headers.get("Range") is not None
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", stream.content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(last - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{last}/{total}")
        self.end_headers()
        if body:
            try:
                self.server.pump(video_id, start, last, self.wfile)
            except (BrokenPipeError, ConnectionResetError):
                pass  # плеер закрыл соединение: перемотка или другой трек


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self._ssl = _ssl_context()
        self._sizes: dict[str, int] = {}

    def _open(self, video_id: str, start: int, end: int, *, fresh: bool = False):
        stream = sources.youtube_stream(video_id, fresh=fresh)
        request = urllib.request.Request(
            stream.url,
            headers={**stream.headers, "Range": f"bytes={start}-{end}"},
        )
        return urllib.request.urlopen(request, timeout=_TIMEOUT, context=self._ssl)

    def _open_fresh_on_403(self, video_id: str, start: int, end: int):
        try:
            return self._open(video_id, start, end)
        except urllib.error.HTTPError as exc:
            if exc.code != 403:
                raise
            return self._open(video_id, start, end, fresh=True)  # ссылка протухла

    def probe_size(self, video_id: str) -> int:
        """Размер файла из Content-Range, когда yt-dlp его не сообщил."""
        size = self._sizes.get(video_id)
        if size is None:
            with self._open_fresh_on_403(video_id, 0, 0) as response:
                content_range = response.headers.get("Content-Range", "")
            found = re.search(r"/(\d+)\s*$", content_range)
            if not found:
                raise RuntimeError("CDN не сообщил размер файла")
            size = self._sizes[video_id] = int(found.group(1))
        return size

    def pump(self, video_id: str, start: int, last: int, out) -> None:
        """Байты start..last (включительно) — кусками, с переподключением."""
        offset = start
        failures = 0
        while offset <= last:
            chunk_end = min(offset + _CHUNK - 1, last)
            try:
                with self._open_fresh_on_403(video_id, offset, chunk_end) as response:
                    while offset <= chunk_end:
                        data = response.read(min(_READ, chunk_end - offset + 1))
                        if not data:
                            break
                        out.write(data)
                        offset += len(data)
                failures = 0
            except (BrokenPipeError, ConnectionResetError):
                raise
            except Exception as exc:
                failures += 1
                if failures > _RECONNECTS:
                    log.warning(
                        "proxy: CDN оборвал %s на %d: %s", video_id, offset, exc
                    )
                    return
                log.info("proxy: переподключение к CDN (%s) @%d", video_id, offset)


class StreamProxy:
    """Сервер в фоновом потоке; url_for() — адрес трека для QMediaPlayer."""

    def __init__(self) -> None:
        self._server = _Server()
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="stream-proxy", daemon=True
        )
        self._thread.start()

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    def url_for(self, video_id: str) -> str:
        return f"http://127.0.0.1:{self.port}/yt/{video_id}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
