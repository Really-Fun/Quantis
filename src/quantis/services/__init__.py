"""Ленивые реэкспорты сервисов — без тяжёлого импорта при `from quantis.services import …`."""

from __future__ import annotations

from typing import Any

__all__ = [
    "AsyncFinder",
    "AsyncStreamer",
    "AsyncDownloader",
    "AsyncRecommendation",
    "AsyncWaveService",
    "TrackHistoryService",
    "LikedTracksService",
    "UserPlaylistsService",
    "MusicService",
]

_LAZY: dict[str, tuple[str, str]] = {
    "AsyncFinder": (".async_finder", "AsyncFinder"),
    "AsyncStreamer": (".async_streamer", "AsyncStreamer"),
    "AsyncDownloader": (".async_downloader", "AsyncDownloader"),
    "AsyncRecommendation": (".async_recommendation", "AsyncRecommendation"),
    "AsyncWaveService": (".async_wave", "AsyncWaveService"),
    "TrackHistoryService": (".track_history", "TrackHistoryService"),
    "LikedTracksService": (".liked_tracks", "LikedTracksService"),
    "UserPlaylistsService": (".user_playlists", "UserPlaylistsService"),
    "MusicService": (".music_service", "MusicService"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr = target
    from importlib import import_module

    module = import_module(module_name, __name__)
    value = getattr(module, attr)
    globals()[name] = value
    return value
