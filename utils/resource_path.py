"""Путь к ресурсам (assets) — в exe они лежат в _MEIPASS."""
import os
import sys


def asset_path(relative: str) -> str:
    """В exe возвращает путь относительно распакованной папки, иначе relative как есть."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        return os.path.join(base, relative)
    return relative
