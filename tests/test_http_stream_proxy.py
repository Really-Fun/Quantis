"""Локальный HTTP-прокси: стрим без файла и reconnect после обрыва CDN."""

from __future__ import annotations

import re
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import ClientSession, web

from quantis.models import YandexTrack
from quantis.services.http_stream_proxy import LocalHttpStreamProxy, _parse_range

_PAYLOAD = bytes(range(256)) * 4096  # 1 MiB


def test_parse_range() -> None:
    assert _parse_range(None) == (0, None)
    assert _parse_range("bytes=100-") == (100, None)
    assert _parse_range("bytes=100-199") == (100, 199)


async def _serve_drop_after(
    payload: bytes, drop_after: int
) -> tuple[web.AppRunner, str]:
    hits = {"n": 0}

    async def handler(request: web.Request) -> web.StreamResponse:
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", request.headers.get("Range", ""))
        start = int(match.group(1)) if match else 0
        end = len(payload) - 1
        if match and match.group(2):
            end = min(int(match.group(2)), end)
        body = payload[start : end + 1]
        hits["n"] += 1
        if hits["n"] == 1 and drop_after < len(body):
            body = body[:drop_after]
        resp = web.StreamResponse(
            status=206,
            headers={
                "Content-Range": (
                    f"bytes {start}-{start + len(body) - 1}/{len(payload)}"
                ),
                "Content-Type": "audio/mpeg",
            },
        )
        await resp.prepare(request)
        await resp.write(body)
        await resp.write_eof()
        return resp

    app = web.Application()
    app.router.add_get("/track.mp3", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{runner.addresses[0][1]}/track.mp3"


@pytest_asyncio.fixture
async def dropped_upstream():
    runner, url = await _serve_drop_after(_PAYLOAD, drop_after=64 * 1024)
    proxy = LocalHttpStreamProxy(AsyncMock(return_value=url))
    track = YandexTrack(track_id="1", title="T", author="A")
    try:
        yield proxy, track, url
    finally:
        await proxy.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_mount_returns_localhost_url(dropped_upstream) -> None:
    proxy, track, url = dropped_upstream
    local = await proxy.mount(track, url)
    assert local.startswith("http://127.0.0.1:")
    assert local.endswith("/yandex/1")


@pytest.mark.asyncio
async def test_proxy_reconnects_after_upstream_drop(dropped_upstream) -> None:
    proxy, track, url = dropped_upstream
    local = await proxy.mount(track, url)
    async with ClientSession() as client:
        async with client.get(local) as resp:
            assert resp.status in (200, 206)
            data = await resp.read()
    assert data == _PAYLOAD


@pytest.mark.asyncio
async def test_proxy_honors_range(dropped_upstream) -> None:
    proxy, track, url = dropped_upstream
    local = await proxy.mount(track, url)
    async with ClientSession() as client:
        async with client.get(local, headers={"Range": "bytes=1000-1999"}) as resp:
            assert resp.status == 206
            data = await resp.read()
    assert data == _PAYLOAD[1000:2000]
