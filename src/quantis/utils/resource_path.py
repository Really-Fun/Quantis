"""Путь к ресурсам (assets) — разработка и PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def _meipass() -> Path | None:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return None


def package_root() -> Path:
    """Корень пакета quantis (рядом с assets/ и styles/)."""
    meipass = _meipass()
    if meipass is not None:
        for candidate in (meipass / "quantis", meipass):
            if (candidate / "assets").is_dir() or (candidate / "styles").is_dir():
                return candidate
        return meipass
    return Path(__file__).resolve().parent.parent


def source_root() -> Path | None:
    """Корень репозитория при запуске из исходников (src/quantis/...)."""
    root = Path(__file__).resolve().parents[3]
    if (root / "pyproject.toml").is_file() and (root / "src" / "quantis").is_dir():
        return root
    return None


def app_dir() -> Path:
    """Каталог приложения: рядом с exe или корень репозитория при разработке.

    Не cwd: запуск из подкаталога (например, styles/) раскладывал там
    credentials/, covers/ и базу истории.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return source_root() or Path.cwd()


def get_asset_path(relative_path: str) -> str:
    """
    Превращает внутренний путь (например, 'assets/icons/play.svg')
    в абсолютный системный путь.
    """
    rel = Path(relative_path)
    meipass = _meipass()
    candidates: list[Path] = []
    if meipass is not None:
        candidates.extend(
            [
                meipass / rel,
                meipass / "quantis" / rel,
            ]
        )
    pkg = package_root()
    candidates.append(pkg / rel)
    if not str(rel).startswith("assets"):
        candidates.append(pkg / "assets" / rel)

    for path in candidates:
        if path.is_file() or path.is_dir():
            return str(path)
    return str(candidates[0] if candidates else pkg / rel)
