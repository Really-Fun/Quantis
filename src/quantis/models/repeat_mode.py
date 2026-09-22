"""Режимы повтора воспроизведения."""

from __future__ import annotations

from enum import Enum


class RepeatMode(str, Enum):
    PLAYLIST = "playlist"
    TRACK = "track"

    def cycle(self) -> RepeatMode:
        if self is RepeatMode.PLAYLIST:
            return RepeatMode.TRACK
        return RepeatMode.PLAYLIST

    @classmethod
    def from_value(cls, raw: str | None) -> RepeatMode:
        if raw == cls.TRACK.value:
            return cls.TRACK
        return cls.PLAYLIST
