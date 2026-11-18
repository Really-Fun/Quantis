"""Хранение постоянных обложек и ограниченного по размеру кэша поиска."""

from __future__ import annotations

import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from threading import RLock

from quantis.models.track import Track
from quantis.providers.library_index import LibraryIndex, track_key
from quantis.providers.path_provider import PathProvider
from quantis.services.cover_validate import cover_bytes_ok, cover_file_ok

logger = logging.getLogger(__name__)
_CACHE_BYTES = 128 * 1024 * 1024
_lock = RLock()


@lru_cache(maxsize=256)
def _playlist_tracks(
    path: Path, mtime_ns: int, size: int
) -> frozenset[tuple[str, str]]:
    from quantis.models.playlist import Playlist

    _, tracks, _ = Playlist.load_playlist(str(path))
    return frozenset(track_key(t.source, str(t.track_id)) for t in tracks)


def in_local_playlist(track: Track) -> bool:
    key = track_key(track.source, str(track.track_id))
    for path in Path(PathProvider.playlists_folder()).glob("*.json"):
        try:
            st = path.stat()
            if key in _playlist_tracks(path, st.st_mtime_ns, st.st_size):
                return True
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return False


def _replace(dest: Path, data: bytes) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dest.parent)
    try:
        with os.fdopen(fd, "wb") as file:
            file.write(data)
        os.replace(tmp, dest)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _trim(folder: Path) -> None:
    entries = []
    total = 0
    for path in folder.glob("*.jpg"):
        try:
            st = path.stat()
        except FileNotFoundError:
            continue
        entries.append((st.st_mtime_ns, path, st.st_size))
        total += st.st_size
    for _, path, size in sorted(entries):
        if total <= _CACHE_BYTES:
            break
        path.unlink(missing_ok=True)
        total -= size


def promote_cover(track: Track) -> None:
    provider = PathProvider()
    with _lock:
        cached = provider.cached_cover_path(track)
        if not cached.is_file():
            return
        permanent = provider.permanent_cover_path(track)
        try:
            data = cached.read_bytes()
            if cover_bytes_ok(data):
                if not cover_file_ok(permanent):
                    _replace(permanent, data)
                cached.unlink(missing_ok=True)
        except OSError:
            logger.warning("Не удалось сохранить обложку %s", track, exc_info=True)


def store_cover(track: Track, data: bytes) -> bool:
    if not cover_bytes_ok(data):
        return False
    provider = PathProvider()
    with _lock:
        if (
            track.downloaded
            or LibraryIndex.instance().has(track.source, str(track.track_id))
            or in_local_playlist(track)
        ):
            _replace(provider.permanent_cover_path(track), data)
        else:
            cached = provider.cached_cover_path(track)
            _replace(cached, data)
            _trim(cached.parent)
    return True
