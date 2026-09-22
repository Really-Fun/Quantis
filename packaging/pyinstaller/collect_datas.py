"""PyInstaller datas: ресурсы без пользовательских секретов и кэша."""

from __future__ import annotations

from pathlib import Path

USER_DATA_DIR_NAMES = frozenset(
    {
        "credentials",
        "covers",
        "music",
        "playlists",
        "playlist_covers",
        "plugins_dir",
        "background",
        "cache",
        "__pycache__",
    }
)
USER_DATA_FILE_NAMES = frozenset(
    {
        "player_history.db",
        "player_history.db-wal",
        "player_history.db-shm",
        "cookie.txt",
        "cookies.txt",
        "portable.txt",
        "youtube_cookies.txt",
        "youtube_cookies.netscape",
    }
)
_STYLE_SUFFIXES = frozenset({".qss", ".css"})
_SKIP_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})


def is_user_data(path: Path, root: Path) -> bool:
    """True, если файл не должен попадать в бандл."""
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = Path(path.name)
    if any(part in USER_DATA_DIR_NAMES for part in rel.parts[:-1]):
        return True
    name = path.name
    if name in USER_DATA_FILE_NAMES or name in USER_DATA_DIR_NAMES:
        return True
    if path.suffix.lower() in _SKIP_SUFFIXES:
        return True
    return False


def collect_dir(
    src: Path,
    dest: str,
    *,
    suffixes: frozenset[str] | None = None,
) -> list[tuple[str, str]]:
    """Файлы ``src`` → dest-каталог PyInstaller, без user-data."""
    items: list[tuple[str, str]] = []
    if not src.is_dir():
        return items
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        if is_user_data(path, src):
            print(f"[Quantis] SKIP user data {path.relative_to(src)}")
            continue
        if suffixes is not None and path.suffix.lower() not in suffixes:
            continue
        rel_parent = path.relative_to(src).parent
        dest_dir = dest if str(rel_parent) == "." else f"{dest}/{rel_parent.as_posix()}"
        items.append((str(path), dest_dir))
    return items


def collect_styles(src: Path) -> list[tuple[str, str]]:
    return collect_dir(src, "quantis/styles", suffixes=_STYLE_SUFFIXES)


def collect_assets(src: Path) -> list[tuple[str, str]]:
    return collect_dir(src, "quantis/assets")
