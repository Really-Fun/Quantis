"""Утилиты для создания и валидации пользовательских плейлистов."""

from __future__ import annotations

import json
import re
from pathlib import Path

_INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*]+')


def create_user_playlist_file(name: str, playlists_dir: str = "playlists") -> Path:
    """Создает пустой JSON-файл пользовательского плейлиста.

    Args:
        name: Отображаемое имя плейлиста.
        playlists_dir: Директория хранения пользовательских плейлистов.

    Returns:
        Path: Путь до созданного файла.

    Raises:
        ValueError: Если имя пустое или состоит только из недопустимых символов.
        FileExistsError: Если плейлист с таким именем уже существует.
    """
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Имя плейлиста не может быть пустым.")

    file_stem = _INVALID_FILE_CHARS.sub("_", clean_name).strip(" .")
    if not file_stem:
        raise ValueError("Имя плейлиста содержит только недопустимые символы.")

    target_dir = Path(playlists_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    playlist_path = target_dir / f"{file_stem}.json"
    if playlist_path.exists():
        raise FileExistsError(f"Плейлист '{clean_name}' уже существует.")

    payload = {
        "name": clean_name,
        "tracks": [],
    }
    playlist_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return playlist_path


def rename_user_playlist_file(
    old_name: str,
    new_name: str,
    playlists_dir: str = "playlists",
) -> Path:
    """Переименовывает пользовательский плейлист и обновляет поле ``name`` в JSON."""
    old_clean = old_name.strip()
    new_clean = new_name.strip()
    if not new_clean:
        raise ValueError("Имя плейлиста не может быть пустым.")

    old_file_stem = _INVALID_FILE_CHARS.sub("_", old_clean).strip(" .")
    new_file_stem = _INVALID_FILE_CHARS.sub("_", new_clean).strip(" .")
    if not old_file_stem or not new_file_stem:
        raise ValueError("Имя плейлиста содержит недопустимые символы.")

    target_dir = Path(playlists_dir)
    old_path = target_dir / f"{old_file_stem}.json"
    if not old_path.exists():
        raise FileNotFoundError("Исходный плейлист не найден.")

    new_path = target_dir / f"{new_file_stem}.json"
    if new_path.exists() and old_path.resolve() != new_path.resolve():
        raise FileExistsError(f"Плейлист '{new_clean}' уже существует.")

    try:
        payload = json.loads(old_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {"name": old_clean, "tracks": []}

    payload["name"] = new_clean
    new_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if old_path.resolve() != new_path.resolve():
        old_path.unlink(missing_ok=True)
    return new_path


def delete_user_playlist_file(name: str, playlists_dir: str = "playlists") -> None:
    """Удаляет JSON-файл пользовательского плейлиста по имени."""
    clean_name = name.strip()
    file_stem = _INVALID_FILE_CHARS.sub("_", clean_name).strip(" .")
    if not file_stem:
        raise ValueError("Имя плейлиста содержит недопустимые символы.")

    playlist_path = Path(playlists_dir) / f"{file_stem}.json"
    if not playlist_path.exists():
        raise FileNotFoundError("Плейлист не найден.")
    playlist_path.unlink()


def list_user_playlist_names(playlists_dir: str = "playlists") -> list[str]:
    """Возвращает список названий пользовательских плейлистов."""
    target_dir = Path(playlists_dir)
    if not target_dir.is_dir():
        return []

    result: list[str] = []
    for playlist_path in sorted(target_dir.glob("*.json")):
        try:
            payload = json.loads(playlist_path.read_text(encoding="utf-8"))
            name = str(payload.get("name", "")).strip()
            result.append(name or playlist_path.stem)
        except Exception:
            result.append(playlist_path.stem)
    return result


def add_track_to_user_playlist(
    playlist_name: str,
    track_id: int | str,
    title: str,
    author: str,
    playlists_dir: str = "playlists",
) -> bool:
    """Добавляет трек в пользовательский плейлист.

    Returns:
        bool: ``True``, если трек был добавлен. ``False``, если уже существовал.
    """
    playlist_path = _find_playlist_path_by_name(playlist_name, playlists_dir)
    payload = _load_playlist_payload(playlist_path)

    tracks = payload.setdefault("tracks", [])
    normalized_id = str(track_id)
    already_exists = any(str(item.get("id", "")) == normalized_id for item in tracks)
    if already_exists:
        return False

    tracks.append(
        {
            "id": normalized_id,
            "title": title,
            "author": author,
        }
    )
    playlist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def remove_track_from_user_playlist(
    playlist_name: str,
    track_id: int | str,
    playlists_dir: str = "playlists",
) -> bool:
    """Удаляет трек из пользовательского плейлиста по ``track_id``.

    Returns:
        bool: ``True``, если трек был удален. ``False`` если трека не было.
    """
    playlist_path = _find_playlist_path_by_name(playlist_name, playlists_dir)
    payload = _load_playlist_payload(playlist_path)

    tracks = payload.setdefault("tracks", [])
    normalized_id = str(track_id)
    new_tracks = [item for item in tracks if str(item.get("id", "")) != normalized_id]
    if len(new_tracks) == len(tracks):
        return False

    payload["tracks"] = new_tracks
    playlist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def _find_playlist_path_by_name(playlist_name: str, playlists_dir: str) -> Path:
    """Находит JSON-файл пользовательского плейлиста по отображаемому имени."""
    clean_name = playlist_name.strip()
    if not clean_name:
        raise ValueError("Имя плейлиста не может быть пустым.")

    target_dir = Path(playlists_dir)
    if not target_dir.is_dir():
        raise FileNotFoundError("Папка плейлистов не найдена.")

    # Сначала точное совпадение по полю name в JSON.
    for playlist_path in sorted(target_dir.glob("*.json")):
        try:
            payload = json.loads(playlist_path.read_text(encoding="utf-8"))
            if str(payload.get("name", "")).strip() == clean_name:
                return playlist_path
        except Exception:
            continue

    # Фолбэк — по имени файла.
    file_stem = _INVALID_FILE_CHARS.sub("_", clean_name).strip(" .")
    fallback_path = target_dir / f"{file_stem}.json"
    if fallback_path.exists():
        return fallback_path
    raise FileNotFoundError(f"Плейлист '{clean_name}' не найден.")


def _load_playlist_payload(path: Path) -> dict:
    """Читает payload плейлиста и нормализует базовую структуру."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {}
    payload.setdefault("name", path.stem)
    payload.setdefault("tracks", [])
    return payload
