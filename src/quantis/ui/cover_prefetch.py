"""Фоновая подгрузка обложек треков для UI."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

from quantis.core.async_bridge import AsyncBridge
from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.services.async_downloader import AsyncDownloader
from quantis.ui.views.widgets.cover_art import invalidate_cover_path

logger = logging.getLogger(__name__)


async def prefetch_track_covers(
    tracks: Iterable[Track],
    downloader: AsyncDownloader,
    *,
    limit: int = 40,
) -> int:
    PathProvider.ensure_storage_dirs()
    count = await downloader.ensure_covers(list(tracks), limit=limit)
    if count:
        for track in list(tracks)[:limit]:
            invalidate_cover_path(PathProvider().get_cover_path(track))
    return count


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
        try:
            await prefetch_track_covers(track_list, downloader, limit=limit)
        except Exception:
            logger.exception("Не удалось подгрузить обложки")
        if on_done is not None:
            bridge.invoke_main(on_done)

    bridge.schedule(_run())
