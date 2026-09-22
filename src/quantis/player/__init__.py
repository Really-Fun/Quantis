"""Публичный API плеера — ленивые импорты."""

from __future__ import annotations

from typing import Any

__all__ = [
    "Player",
    "QtMediaEngine",
    "create_media_engine",
]


def __getattr__(name: str) -> Any:
    if name == "Player":
        from quantis.player.player import Player

        return Player
    if name == "QtMediaEngine":
        from quantis.player.engine import QtMediaEngine

        return QtMediaEngine
    if name == "create_media_engine":
        from quantis.player.factory import create_media_engine

        return create_media_engine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
