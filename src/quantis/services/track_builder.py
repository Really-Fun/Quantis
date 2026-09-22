"""Сборка Track из записей БД."""

from __future__ import annotations

from quantis.models import SoundCloudTrack, Track, YandexTrack, YoutubeTrack
from quantis.providers import TrackManager


def split_track_key(track_key: str, source_fallback: str) -> tuple[str, str]:
    """Разбивает ключ ``source:id`` на составляющие."""
    if ":" not in track_key:
        return source_fallback or "youtube", track_key
    source, raw_id = track_key.split(":", 1)
    return source or source_fallback, raw_id


def build_track_key(track: Track) -> str:
    return f"{track.source}:{track.track_id}"


def build_tracks_from_entries(
    entries: list[dict],
    track_manager: TrackManager | None = None,
    *,
    include_listen_count: bool = False,
) -> list[Track]:
    manager = track_manager or TrackManager()
    tracks: list[Track] = []
    for entry in entries:
        source, track_id = split_track_key(entry["track_key"], entry["source"])
        downloaded = manager.is_downloaded(str(track_id), source=source)
        kwargs: dict = {
            "title": entry["title"],
            "author": entry["author"],
            "downloaded": downloaded,
            "duration_ms": max(0, int(entry.get("duration_ms") or 0)),
        }
        if include_listen_count:
            kwargs["listen_count"] = int(entry.get("listen_count", 0))
        if source == "yandex":
            tracks.append(
                YandexTrack(
                    track_id=int(track_id) if str(track_id).isdigit() else track_id,
                    **kwargs,
                )
            )
        elif source == "soundcloud":
            tracks.append(SoundCloudTrack(track_id=str(track_id), **kwargs))
        else:
            tracks.append(YoutubeTrack(track_id=str(track_id), **kwargs))
    return tracks
