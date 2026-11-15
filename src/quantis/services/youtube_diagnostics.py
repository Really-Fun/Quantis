"""Проверка полного пути YouTube: соединение, извлечение, аудиопоток."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from aiohttp import ClientSession, ClientTimeout

from quantis.core.worker_pool import get_worker_pool
from quantis.models import YoutubeTrack
from quantis.services.http_stream_proxy import LocalHttpStreamProxy
from quantis.services.net_proxy import check_youtube, proxy_label
from quantis.services.youtube_streamer import AsyncYoutubeStreamer

logger = logging.getLogger(__name__)
_TEST_VIDEO_ID = "dQw4w9WgXcQ"


async def check_youtube_full(
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    """Читает фрагмент аудио по тому же пути, что плеер; звук не включает."""
    report = progress or (lambda text: None)
    stage = "1/3 — соединение с YouTube"
    streamer = None
    proxy = None
    route = proxy_label() or "напрямую"
    try:
        report(f"{stage}…")
        ok, message = await check_youtube()
        if not ok:
            return False, f"{stage}: ошибка.\n{message}"
        stage = "2/3 — получение ссылки на аудио"
        report(f"✓ Соединение установлено.\n{stage}…")
        streamer = AsyncYoutubeStreamer(get_worker_pool())
        track = YoutubeTrack(
            track_id=_TEST_VIDEO_ID, title="Проверка YouTube", author=""
        )
        url = await asyncio.wait_for(streamer.get_stream_url(track), timeout=60)
        if not url:
            return False, (
                f"{stage}: ошибка. YouTube отвечает, но ссылка на аудио не получена. "
                "Подробности записаны в quantis.log."
            )
        stage = "3/3 — загрузка аудио"
        report(f"✓ Соединение и ссылка получены.\n{stage}…")

        async def refresh(_track):
            streamer.invalidate(str(_track.track_id))
            return await streamer.get_stream_url(_track)

        proxy = LocalHttpStreamProxy(refresh, shutdown_timeout=1.0)
        local_url = await proxy.mount(track, url)
        async with ClientSession(timeout=ClientTimeout(total=30)) as client:
            async with client.get(
                local_url, headers={"Range": "bytes=0-65535"}
            ) as response:
                if response.status not in (200, 206):
                    return (
                        False,
                        f"{stage}: ошибка HTTP {response.status}. Подробности в quantis.log.",
                    )
                content_type = response.headers.get("Content-Type", "").lower()
                try:
                    data = await response.content.readexactly(65536)
                except asyncio.IncompleteReadError as exc:
                    data = exc.partial
                if not data or "text/" in content_type or "json" in content_type:
                    return (
                        False,
                        f"{stage}: вместо аудио получен пустой ответ или страница ошибки.",
                    )
        return True, (
            f"✓ 3/3 — проверка пройдена ({route}).\n"
            f"YouTube отвечает, ссылка получена, аудиоданные загружены ({len(data)} байт).\n"
            "Проверен тестовый ролик; доступность других треков может отличаться."
        )
    except TimeoutError:
        return False, f"{stage}: превышено время ожидания."
    except Exception:
        logger.exception("Полная проверка YouTube: %s", stage)
        return False, f"{stage}: ошибка. Подробности записаны в quantis.log."
    finally:
        if proxy is not None:
            await proxy.close()
        if streamer is not None:
            streamer.close()
