"""Тесты прогрессивного буфера: быстрый старт и перемотка по диапазонам."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import web

from quantis.models import YandexTrack
from quantis.services.yandex_progressive_buffer import ProgressiveStreamBuffer

# Больше _AHEAD_BYTES, иначе загрузка успевает закончиться до перемотки.
_PAYLOAD = bytes(range(256)) * 32768  # 8 MiB
_DURATION_MS = 200_000


def _size(path: str) -> int:
    return Path(path).stat().st_size


def _read(path: str) -> bytes:
    return Path(path).read_bytes()


async def _serve(payload: bytes) -> tuple[web.AppRunner, str]:
    async def handler(request: web.Request) -> web.Response:
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", request.headers.get("Range", ""))
        if match is None:
            return web.Response(body=payload)
        start = int(match.group(1))
        if start >= len(payload):
            return web.Response(status=416)
        end = min(int(match.group(2)), len(payload) - 1)
        return web.Response(
            status=206,
            body=payload[start : end + 1],
            headers={"Content-Range": f"bytes {start}-{end}/{len(payload)}"},
        )

    app = web.Application()
    app.router.add_get("/track.mp3", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    return runner, f"http://127.0.0.1:{runner.addresses[0][1]}/track.mp3"


@pytest_asyncio.fixture
async def stream():
    runner, url = await _serve(_PAYLOAD)
    buffer = ProgressiveStreamBuffer(AsyncMock(return_value=url))
    track = YandexTrack(track_id="1", title="T", author="A", duration_ms=_DURATION_MS)
    try:
        yield buffer, track, url
    finally:
        await buffer.close()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_open_gives_full_size_file_immediately(stream) -> None:
    buffer, track, url = stream

    path = await buffer.open(track, url=url)

    assert path is not None
    # Файл сразу полного размера: Qt видит верную длительность и может seek.
    assert _size(path) == len(_PAYLOAD)
    assert _read(path)[:65536] == _PAYLOAD[:65536]


@pytest.mark.asyncio
async def test_seek_downloads_requested_region(stream) -> None:
    buffer, track, url = stream
    path = await buffer.open(track, url=url)
    assert path is not None

    position_ms = int(_DURATION_MS * 0.9)
    offset = buffer._offset_for_ms(position_ms)
    assert offset is not None
    assert not buffer._is_downloaded(offset, offset + 4096)

    await buffer.seek_to_ms(track, position_ms)

    data = _read(path)
    assert data[offset : offset + 4096] == _PAYLOAD[offset : offset + 4096]


@pytest.mark.asyncio
async def test_reopen_same_track_keeps_progress(stream) -> None:
    buffer, track, url = stream
    first_path = await buffer.open(track, url=url)
    task = buffer._task

    second_path = await buffer.open(track, url=url)

    # Восстановление потока не должно стирать буфер и качать всё заново.
    assert second_path == first_path
    assert buffer._task is task


@pytest.mark.asyncio
async def test_owns_only_its_own_temp_file(stream) -> None:
    buffer, track, url = stream
    path = await buffer.open(track, url=url)

    assert buffer.owns(path)
    assert not buffer.owns("/music/library/track.mp3")
    assert not buffer.owns(None)


def test_range_map_tracks_gaps() -> None:
    buffer = ProgressiveStreamBuffer(AsyncMock())
    buffer._total = 1000

    buffer._mark(0, 100)
    buffer._mark(400, 600)
    buffer._mark(100, 200)

    assert buffer._ranges == [(0, 200), (400, 600)]
    assert buffer._prefix_bytes() == 200
    # После перемотки в 400 голова продолжает с конца скачанного куска.
    assert buffer._next_offset(400) == 600
    # Дойдя до конца, возвращаемся закрывать пропуск.
    assert buffer._next_offset(1000) == 200
    assert buffer._is_downloaded(400, 600)
    assert not buffer._is_downloaded(200, 400)

    buffer._mark(200, 400)
    buffer._mark(600, 1000)
    assert buffer._first_gap() is None
    assert buffer._next_offset(0) is None


@pytest.mark.asyncio
async def test_wait_for_more_prefix_reaches_target(stream) -> None:
    buffer, track, url = stream
    await buffer.open(track, url=url)
    start = buffer._prefix_bytes()

    ok = await buffer.wait_for_more_prefix(track, extra_bytes=64 * 1024, timeout=4.0)

    assert ok is True
    assert buffer._prefix_bytes() >= start + 64 * 1024


def test_report_position_moves_playhead_and_wakes() -> None:
    buffer = ProgressiveStreamBuffer(AsyncMock())
    buffer._track_key = "yandex:1"
    buffer._total = 1_000_000
    buffer._duration_ms = 200_000
    buffer._mark(0, 100_000)
    track = YandexTrack(track_id="1", title="T", author="A", duration_ms=200_000)

    buffer.report_position_ms(track, 80_000)

    assert buffer._play_offset > 0
    assert buffer._wake.is_set()
