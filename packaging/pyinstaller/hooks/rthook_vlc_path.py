"""Подключает bundled / system libVLC для frozen-сборки."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _setup() -> None:
    if not getattr(sys, "frozen", False):
        return
    base = Path(sys.executable).resolve().parent
    plugins = base / "plugins"
    if plugins.is_dir():
        os.environ.setdefault("VLC_PLUGIN_PATH", str(plugins))
        os.environ.setdefault("VLC_HOME", str(base))

    # libvlc.dll рядом с exe
    path = os.environ.get("PATH", "")
    prefix = str(base)
    if prefix.lower() not in path.lower():
        os.environ["PATH"] = prefix + os.pathsep + path


_setup()
