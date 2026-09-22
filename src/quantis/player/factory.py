"""Фабрика медиадвижков."""

from __future__ import annotations

import logging

from quantis.config.media_backend import MediaBackendId, resolve_media_backend
from quantis.player.base import MediaEngine
from quantis.player.engine import QtMediaEngine

logger = logging.getLogger(__name__)


def create_media_engine(backend: MediaBackendId | None = None) -> MediaEngine:
    chosen = backend or resolve_media_backend()
    if chosen == "vlc":
        try:
            from quantis.player.vlc_engine import VlcMediaEngine

            engine = VlcMediaEngine()
            logger.info("Медиадвижок: VLC")
            return engine
        except Exception:
            logger.exception(
                "VLC недоступен — fallback на Qt Multimedia. "
                "Установите VLC и python-vlc, либо соберите Quantis-VLC."
            )
    logger.info("Медиадвижок: Qt Multimedia")
    return QtMediaEngine()
