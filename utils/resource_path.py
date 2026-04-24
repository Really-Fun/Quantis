"""Путь к ресурсам (assets)"""
import os
import sys


def asset_path(relative: str) -> str:
    """В exe — абсолютный путь от папки с exe, иначе relative как есть."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
        return os.path.normpath(os.path.join(base, relative))
    return relative