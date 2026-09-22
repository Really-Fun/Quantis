"""Выбор медиадвижка: qt | vlc.

Приоритет:
1. ``QUANTIS_MEDIA_BACKEND`` (env)
2. Константа сборки ``_BUILD_BACKEND`` (подставляется PyInstaller)
3. ``qt`` по умолчанию
"""

from __future__ import annotations

import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

MediaBackendId = Literal["qt", "vlc"]

# PyInstaller / build_exe.py может перезаписать через --runtime-hook или patch.
_BUILD_BACKEND: MediaBackendId | None = None


def _normalize(raw: str | None) -> MediaBackendId | None:
    if not raw:
        return None
    value = raw.strip().lower()
    if value in ("qt", "qtmultimedia", "ffmpeg", "qmediaplayer"):
        return "qt"
    if value in ("vlc", "libvlc", "python-vlc"):
        return "vlc"
    return None


def resolve_media_backend() -> MediaBackendId:
    env = _normalize(os.environ.get("QUANTIS_MEDIA_BACKEND"))
    if env is not None:
        return env
    if _BUILD_BACKEND in ("qt", "vlc"):
        return _BUILD_BACKEND
    return "qt"


def backend_display_name(backend: MediaBackendId | None = None) -> str:
    bid = backend or resolve_media_backend()
    return "VLC (libvlc)" if bid == "vlc" else "Qt Multimedia"
