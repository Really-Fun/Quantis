"""Каталог статичных обоев (background/user и assets/background)."""

from __future__ import annotations

from pathlib import Path

from quantis.utils import app_paths, get_asset_path

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# Встроенные обои переименованы (и пережаты) — старые пути из настроек
# сопоставляем с новыми, чтобы выбор пользователя не сбрасывался.
_RENAMED_BUNDLED = {
    "1352905.png": "neon-city.jpg",
    "real.jpg": "neon-drive.jpg",
    "the-shorekeeper-3840x2160-25523.jpg": "shorekeeper.jpg",
    "wall0.png": "aurora-drop.jpg",
    "wall1.png": "triangles.jpg",
    "wall2.png": "night-train.jpg",
    "wallhalla-84-2560x1600.jpg": "nebula.jpg",
    "majestic-mountain-peak-tranquil-winter-landscape-generated-by-ai.jpg": (
        "winter-peak.jpg"
    ),
}


def user_backgrounds_dir() -> Path:
    """Папка пользовательских обоев: background/user/ в каталоге данных."""
    return app_paths.user_backgrounds_dir()


def bundled_backgrounds_dir() -> Path:
    return Path(get_asset_path("assets/background"))


def is_wallpaper_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS


def wallpaper_dirs() -> list[Path]:
    """Встроенные обои (read-only) и пользовательские (записываемые)."""
    return [
        bundled_backgrounds_dir(),
        user_backgrounds_dir(),
    ]


def scan_wallpapers() -> list[Path]:
    """Все доступные изображения из встроенных и пользовательских папок."""
    found: list[Path] = []
    seen: set[str] = set()
    for folder in wallpaper_dirs():
        if not folder.is_dir():
            continue
        for entry in sorted(folder.iterdir()):
            if not is_wallpaper_file(entry):
                continue
            key = str(entry.resolve())
            if key in seen:
                continue
            seen.add(key)
            found.append(entry)
    return found


def wallpaper_display_name(path: Path) -> str:
    try:
        if path.resolve().parent == user_backgrounds_dir().resolve():
            return f"Мои — {path.stem}"
    except OSError:
        pass
    return path.stem


def default_wallpaper_path() -> str:
    for folder in wallpaper_dirs():
        for name in ("winter-peak.jpg", "wallpaper.jpg"):
            path = folder / name
            if path.is_file():
                return str(path.resolve())
    for path in scan_wallpapers():
        return str(path.resolve())
    return ""


def remap_renamed_wallpaper(stored: str | None) -> str | None:
    """Новый путь для встроенных обоев, переименованных при пережатии."""
    if not stored:
        return None
    renamed = _RENAMED_BUNDLED.get(Path(stored).name)
    if not renamed:
        return None
    candidate = bundled_backgrounds_dir() / renamed
    return str(candidate.resolve()) if candidate.is_file() else None


def resolve_wallpaper_path(stored: str | None = None) -> str:
    if stored:
        chosen = Path(stored)
        if chosen.is_file() and is_wallpaper_file(chosen):
            return str(chosen.resolve())
        remapped = remap_renamed_wallpaper(stored)
        if remapped:
            return remapped
    return default_wallpaper_path()
