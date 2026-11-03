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
    """Теги из имени файла, когда сервис чисто ответил «нет такого трека»."""
    from quantis.models.track import strip_youtube_stats

    author = (entry.author or "").strip()
    if entry.source == "youtube" and author:
        author = strip_youtube_stats(author)
    return TrackMeta(
        source=entry.source,
        track_id=entry.track_id,
        title=(entry.title or "").strip(),
        artist=author,
        source_url=source_url(entry.source, entry.track_id),
    )


def _readings(entry: IndexEntry) -> list[tuple[str, str]]:
    if not entry.ambiguous:
        return [(entry.source, entry.track_id)]
    return [(r.source, r.track_id) for r in parse_legacy_names(entry.path.name)]


def _title_matches(service_title: str, name_rest: str) -> bool:
    """Название сервиса совпадает с началом имени после ID.

    Старые имена санитизировались `_sanitize_filename_part` (``? : / " * | %``
    и т. п. -> ``_``), а название и исполнитель склеены через ``_``, поэтому
    сравниваем санитизированное название с началом остатка имени.
    """
    from quantis.providers.path_provider import PathProvider

    if not (service_title or "").strip():
        return False
    title = PathProvider._sanitize_filename_part(service_title).casefold()
    rest = name_rest.casefold()
    return rest == title or rest.startswith(title + "_")


async def _resolve(downloader: AsyncDownloader, entry: IndexEntry):
    """(entry, track, meta) для записи; None — пропустить файл без изменений.

    Ошибка сервиса (сеть, лимит 429) — это не «трека нет»: файл пропускается,
    чтобы следующий запуск обработал его заново.
    """
    from quantis.models.playlist import _track_from_entry

    if not entry.ambiguous:
        track = _track_from_entry(entry)
        if track is None:
            return None
        try:
            meta = await downloader.lookup_meta(track)
        except Exception:
            logger.info(
                "Сервис недоступен, файл пропущен: %s", entry.path, exc_info=True
            )
            return None
        return entry, track, meta or _fallback_meta(entry)

    stem = entry.path.stem
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
        try:
            meta = await downloader.lookup_meta(track)
        except Exception:
            # Не знаем, есть ли этот трек: выбирать другое прочтение нельзя.
            logger.info(
                "Сервис недоступен, файл пропущен: %s", entry.path, exc_info=True
            )
            return None
        rest = stem[len(reading.track_id) + 1 :]
        # Сырое название сервиса: meta.title у YouTube может быть из имени файла.
        if meta is not None and _title_matches(meta.service_title or meta.title, rest):
            found.append((candidate, track, meta))
    # Без однозначного проверенного ответа сервиса не гадаем по имени файла.
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
            readings = _readings(entry)
            if not downloader.begin_retag(readings):
                # Файл может быть недокачан: им владеет скачивание.
                report.skipped += 1
                if on_progress is not None:
                    on_progress(i, total)
                continue
            try:
                resolved = await _resolve(downloader, entry)
                if resolved is None:
                    report.skipped += 1
                else:
                    resolved_entry, track, meta = resolved
                    outcome = await downloader.tag_and_rename(
                        resolved_entry.path, meta, track
                    )
                    # Теги без нового имени — не готово: файл ещё `ID_…`.
                    if outcome.complete:
                        report.done += 1
                    else:
                        report.skipped += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Не удалось обработать %s", entry.path, exc_info=True)
                report.skipped += 1
            finally:
                downloader.end_retag(readings)
        if on_progress is not None:
            on_progress(i, total)
    return report
