"""Фоновая подгрузка обложек треков для UI."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from quantis.core.async_bridge import AsyncBridge
from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.services.async_downloader import AsyncDownloader
from quantis.services.cover_validate import cover_file_ok
from quantis.ui.views.widgets.cover_art import notify_cover_ready, track_cover_file

logger = logging.getLogger(__name__)


async def prefetch_track_covers(
    tracks: Iterable[Track],
    downloader: AsyncDownloader,
    *,
    limit: int = 40,
) -> list[str]:
    """Качает недостающие обложки; возвращает пути тех, что появились."""
    PathProvider.ensure_storage_dirs()
    track_list = list(tracks)[: max(0, limit)]
    missing = [
        str(path)
        for path in dict.fromkeys(track_cover_file(t) for t in track_list)
        if not cover_file_ok(path)
    ]
    if not missing:
        return []
    count = await downloader.ensure_covers(track_list, limit=limit)
    if not count:
        return []
    return [path for path in missing if cover_file_ok(path)]


def schedule_cover_prefetch(
    tracks: Iterable[Track],
    downloader: AsyncDownloader,
    bridge: AsyncBridge,
    on_done: Callable[[], None] | None = None,
    *,
    limit: int = 40,
) -> None:
    track_list = list(tracks)

    async def _run() -> None:
        fresh: list[str] = []
        try:
            fresh = await prefetch_track_covers(track_list, downloader, limit=limit)
        except Exception:
            logger.exception("Не удалось подгрузить обложки")
        if not fresh and on_done is None:
            return

        def _announce() -> None:
            # Кэш обложек и подписчики живут в главном потоке.
            for path in fresh:
                notify_cover_ready(path)
            if on_done is not None:
                on_done()

        bridge.invoke_main(_announce)

    bridge.schedule(_run())
