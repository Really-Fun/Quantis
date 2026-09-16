"""Фиксирует медиадвижок VLC для этой сборки."""

from __future__ import annotations

import os

os.environ.setdefault("QUANTIS_MEDIA_BACKEND", "vlc")

try:
    from quantis.config import media_backend as mb

    mb._BUILD_BACKEND = "vlc"
except Exception:
    pass
