"""Фиксирует медиадвижок Qt для этой сборки."""

from __future__ import annotations

import os

os.environ.setdefault("QUANTIS_MEDIA_BACKEND", "qt")

try:
    from quantis.config import media_backend as mb

    mb._BUILD_BACKEND = "qt"
except Exception:
    pass
