"""Записываемые каталоги приложения.

Ресурсы из комплекта (assets, styles) читаются через ``resource_path`` и всегда
лежат рядом с exe — они read-only. Всё, что приложение пишет, идёт сюда.

Порядок выбора корня данных:

1. ``QUANTIS_DATA_DIR`` — явное указание, приоритетнее всего;
2. портативный режим (``QUANTIS_PORTABLE=1`` или файл-маркер ``portable.txt``
   рядом с exe) — данные рядом с exe;
3. запуск из исходников — корень проекта (историческое поведение, чтобы
   разработка и тесты не зависели от каталогов пользователя);
4. иначе — пользовательский каталог ОС: ``%LOCALAPPDATA%\\Quantis`` на Windows,
   ``$XDG_DATA_HOME/quantis`` на Linux, ``~/Library/Application Support`` на macOS.

Если выбранный корень оказался недоступен для записи (типовой случай —
портативная сборка, установленная в ``C:\\Program Files``), приложение молча
переезжает в пользовательский каталог ОС вместо падения с ошибкой прав.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

from quantis.utils.resource_path import app_dir

logger = logging.getLogger(__name__)

APP_DIR_NAME = "Quantis"
_XDG_DIR_NAME = "quantis"
_PORTABLE_MARKERS = ("portable.txt", "portable", ".portable")
_MIGRATION_MARKER = ".migrated"

_TRUTHY = ("1", "true", "yes", "on")

# Каталоги и файлы, которые переносим со старой раскладки (рядом с exe).
_LEGACY_ENTRIES = (
    "music",
    "covers",
    "playlists",
    "playlist_covers",
    "credentials",
    "plugins_dir",
    "background",
    "player_history.db",
    "player_history.db-wal",
    "player_history.db-shm",
)

_data_dir: Path | None = None
_cache_dir: Path | None = None
_music_dir: Path | None = None


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUTHY


def _env_path(name: str) -> Path | None:
    raw = os.environ.get(name, "").strip()
    return Path(raw).expanduser() if raw else None


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_portable() -> bool:
    """Портативный режим: данные лежат рядом с exe."""
    if _env_flag("QUANTIS_PORTABLE"):
        return True
    if not is_frozen():
        return False
    return any((app_dir() / marker).exists() for marker in _PORTABLE_MARKERS)


def _platform_data_dir() -> Path:
    if sys.platform == "win32":
        base = _env_path("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return base / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME
    base = _env_path("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return base / _XDG_DIR_NAME


def _platform_cache_dir() -> Path:
    if sys.platform == "win32":
        base = _env_path("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return base / APP_DIR_NAME / "cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / APP_DIR_NAME
    base = _env_path("XDG_CACHE_HOME") or Path.home() / ".cache"
    return base / _XDG_DIR_NAME


def _is_writable(path: Path) -> bool:
    """Проверяет, что каталог существует (или создаётся) и доступен для записи."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    probe = path / ".write-test"
    try:
        probe.touch()
        probe.unlink()
    except OSError:
        return False
    return True


def data_dir() -> Path:
    """Корень пользовательских данных. Гарантированно доступен для записи."""
    global _data_dir
    if _data_dir is not None:
        return _data_dir

    explicit = _env_path("QUANTIS_DATA_DIR")
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    elif is_portable() or not is_frozen():
        candidates.append(app_dir())
    candidates.append(_platform_data_dir())
    candidates.append(Path(tempfile.gettempdir()) / APP_DIR_NAME)

    preferred = candidates[0]
    for candidate in candidates:
        if _is_writable(candidate):
            if candidate != preferred:
                logger.warning(
                    "Каталог данных %s недоступен для записи, используем %s",
                    preferred,
                    candidate,
                )
            _data_dir = candidate
            return _data_dir

    # Ни один вариант не подошёл: возвращаем платформенный путь, чтобы ошибка
    # прав всплыла в логе на первой же записи, а не была проглочена здесь.
    _data_dir = _platform_data_dir()
    return _data_dir


def cache_dir() -> Path:
    """Кэш: временные загрузки, распаковка плагинов."""
    global _cache_dir
    if _cache_dir is not None:
        return _cache_dir
    root = data_dir()
    candidate = (
        _platform_cache_dir() if root == _platform_data_dir() else root / "cache"
    )
    if not _is_writable(candidate):
        candidate = root / "cache"
        candidate.mkdir(parents=True, exist_ok=True)
    _cache_dir = candidate
    return _cache_dir


def default_music_dir() -> Path:
    """Куда складывать скачанное по умолчанию.

    В портативном режиме и при запуске из исходников — рядом с остальными
    данными, иначе — ``Музыка/Quantis``, чтобы файлы были видны в проводнике.
    """
    root = data_dir()
    if is_portable() or not is_frozen() or root != _platform_data_dir():
        return root / "music"
    home_music = Path.home() / "Music"
    if home_music.is_dir():
        return home_music / APP_DIR_NAME
    return root / "music"


def _stored_music_dir() -> Path | None:
    """Путь из настроек (QSettings), если пользователь его менял."""
    try:
        from PySide6.QtCore import QSettings
    except ImportError:
        return None
    try:
        raw = QSettings("ReallyFun", "Quantis").value("storage/music_dir", "")
    except Exception:  # pragma: no cover - QSettings без QApplication
        return None
    text = str(raw).strip() if raw else ""
    return Path(text).expanduser() if text else None


def music_dir() -> Path:
    """Каталог скачанных треков (с учётом настройки пользователя)."""
    global _music_dir
    if _music_dir is not None:
        return _music_dir
    stored = _stored_music_dir()
    candidate = stored or default_music_dir()
    if not _is_writable(candidate):
        fallback = default_music_dir()
        if candidate != fallback and _is_writable(fallback):
            logger.warning(
                "Папка музыки %s недоступна для записи, используем %s",
                candidate,
                fallback,
            )
            candidate = fallback
    _music_dir = candidate
    return _music_dir


def _subdir(name: str) -> Path:
    path = data_dir() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def covers_dir() -> Path:
    return _subdir("covers")


def playlists_dir() -> Path:
    return _subdir("playlists")


def playlist_covers_dir() -> Path:
    return _subdir("playlist_covers")


def credentials_dir() -> Path:
    path = _subdir("credentials")
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def user_plugins_dir() -> Path:
    """Плагины пользователя (записываемые)."""
    return _subdir("plugins_dir")


def bundled_plugins_dir() -> Path:
    """Плагины из комплекта поставки рядом с exe (read-only)."""
    return app_dir() / "plugins_dir"


def user_backgrounds_dir() -> Path:
    path = data_dir() / "background" / "user"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return data_dir() / "player_history.db"


def ensure_dirs() -> None:
    """Создаёт всё, что нужно приложению для работы."""
    music_dir().mkdir(parents=True, exist_ok=True)
    for factory in (covers_dir, playlists_dir, credentials_dir, user_plugins_dir):
        factory()


def reset_cache() -> None:
    """Сбрасывает запомненные пути (настройки, тесты)."""
    global _data_dir, _cache_dir, _music_dir
    _data_dir = None
    _cache_dir = None
    _music_dir = None


def reset_music_dir_cache() -> None:
    """Точечный сброс после смены папки музыки в настройках."""
    global _music_dir
    _music_dir = None


def migrate_legacy_data() -> None:
    """Переносит данные из старой раскладки (рядом с exe) в каталог данных.

    До версии с ``app_paths`` всё писалось в рабочий каталог или рядом с exe.
    Копируем (не переносим) — источник может быть read-only, а терять данные
    пользователя из-за прав нельзя.
    """
    target = data_dir()
    legacy = app_dir()
    try:
        same = target.resolve() == legacy.resolve()
    except OSError:
        same = False
    if same:
        return

    marker = target / _MIGRATION_MARKER
    if marker.exists():
        return

    copied: list[str] = []
    for name in _LEGACY_ENTRIES:
        source = legacy / name
        if not source.exists():
            continue
        destination = target / name
        if destination.exists():
            continue
        try:
            if source.is_dir():
                shutil.copytree(source, destination)
            else:
                shutil.copy2(source, destination)
        except OSError:
            logger.exception("Не удалось перенести %s в %s", source, destination)
            continue
        copied.append(name)

    if copied:
        logger.info("Данные перенесены из %s: %s", legacy, ", ".join(copied))
    try:
        marker.write_text("", encoding="utf-8")
    except OSError:
        logger.debug("Не удалось создать маркер миграции в %s", target)


def describe() -> dict[str, str]:
    """Сводка путей — для страницы настроек и логов."""
    return {
        "Данные": str(data_dir()),
        "Музыка": str(music_dir()),
        "Обложки": str(covers_dir()),
        "Плейлисты": str(playlists_dir()),
        "Плагины": str(user_plugins_dir()),
        "База": str(database_path()),
        "Кэш": str(cache_dir()),
    }
