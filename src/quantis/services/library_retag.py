"""Миграция старых файлов `ID_Название_Исполнитель.ext`: теги и новое имя."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from quantis.providers.legacy_names import parse_legacy_names
from quantis.services.track_tags import TrackMeta, source_url

if TYPE_CHECKING:
    from quantis.providers.library_index import IndexEntry, LibraryIndex
    from quantis.services.async_downloader import AsyncDownloader

logger = logging.getLogger(__name__)


@dataclass
class RetagReport:
    done: int = 0
    already: int = 0
    skipped: int = 0


def _fallback_meta(entry: IndexEntry) -> TrackMeta:
    return TrackMeta(
        source=entry.source,
        track_id=entry.track_id,
        title=entry.title,
        artist=entry.author or "",
        source_url=source_url(entry.source, entry.track_id),
    )


async def _safe_fetch(downloader: AsyncDownloader, track) -> TrackMeta | None:
    try:
        return await downloader.fetch_meta(track)
    except Exception:
        logger.debug("Метаданные недоступны: %s", track, exc_info=True)
        return None


async def _resolve(downloader: AsyncDownloader, entry: IndexEntry):
    """(entry, track, meta) для записи; None, если прочтение имени неоднозначно."""
    from quantis.models.playlist import _track_from_entry

    if not entry.ambiguous:
        track = _track_from_entry(entry)
        if track is None:
            return None
        meta = await _safe_fetch(downloader, track) or _fallback_meta(entry)
        return entry, track, meta

    found = []
    for reading in parse_legacy_names(entry.path.name):
        candidate = dataclasses.replace(
            entry,
            source=reading.source,
            track_id=reading.track_id,
            title=reading.title,
            author=reading.author,
            ambiguous=False,
        )
        track = _track_from_entry(candidate)
        if track is None:
            continue
        meta = await _safe_fetch(downloader, track)
        if meta is not None:
            found.append((candidate, track, meta))
    # Без однозначного ответа сервиса не гадаем по имени файла.
    return found[0] if len(found) == 1 else None


async def retag_legacy(
    downloader: AsyncDownloader,
    index: LibraryIndex,
    on_progress: Callable[[int, int], None] | None = None,
) -> RetagReport:
    """Вшивает теги и переименовывает старые файлы. Последовательно: лимит Яндекса."""
    await index.refresh()
    entries = index.entries()
    total = len(entries)
    report = RetagReport()
    for i, entry in enumerate(entries, start=1):
        if entry.tagged:
            report.already += 1
        else:
            try:
                resolved = await _resolve(downloader, entry)
                if resolved is None:
                    report.skipped += 1
                else:
                    resolved_entry, track, meta = resolved
                    final = await downloader.tag_and_rename(
                        resolved_entry.path, meta, track
                    )
                    if final is None:
                        report.skipped += 1
                    else:
                        report.done += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Не удалось обработать %s", entry.path, exc_info=True)
                report.skipped += 1
        if on_progress is not None:
            on_progress(i, total)
    return report
