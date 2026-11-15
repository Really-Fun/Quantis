import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from aiohttp import web

from quantis.services import youtube_diagnostics as diagnostic


@pytest.mark.asyncio
async def test_reports_connectivity_failure_without_resolving():
    with patch.object(
        diagnostic, "check_youtube", AsyncMock(return_value=(False, "нет связи"))
    ):
        ok, text = await diagnostic.check_youtube_full()
    assert not ok
    assert "1/3" in text and "нет связи" in text


@pytest.mark.asyncio
async def test_reports_missing_audio_formats():
    with (
        patch.object(diagnostic, "check_youtube", AsyncMock(return_value=(True, "OK"))),
        patch.object(
            diagnostic.AsyncYoutubeStreamer,
            "get_stream_url",
            AsyncMock(return_value=None),
        ),
    ):
        ok, text = await diagnostic.check_youtube_full()
    assert not ok
    assert "2/3" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload,status,expected",
    [(b"audio" * 1000, 206, True), (b"", 206, False), (b"error", 403, False)],
)
async def test_checks_actual_audio_through_player_proxy(payload, status, expected):
    async def audio(request):
        response = web.StreamResponse(
            status=status,
            headers={"Content-Type": "audio/mp4", "Content-Length": str(len(payload))},
        )
        await response.prepare(request)
        await response.write(payload[:100])
        await asyncio.sleep(0.01)
        await response.write(payload[100:])
        await response.write_eof()
        return response

    app = web.Application()
    app.router.add_get("/audio", audio)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    url = f"http://127.0.0.1:{runner.addresses[0][1]}/audio"
    try:
        with (
            patch.object(
                diagnostic, "check_youtube", AsyncMock(return_value=(True, "OK"))
            ),
            patch.object(
                diagnostic.AsyncYoutubeStreamer,
                "get_stream_url",
                AsyncMock(return_value=url),
            ),
        ):
            ok, text = await diagnostic.check_youtube_full()
        assert ok is expected
        if expected:
            assert f"{len(payload)} байт" in text
        assert "3/3" in text
    finally:
        await runner.cleanup()
