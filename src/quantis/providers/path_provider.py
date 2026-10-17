from __future__ import annotations

import glob
import logging
import re
from os import path
from pathlib import Path

from quantis.models.track import Track, TrackSource
from quantis.services.soundcloud import storage_id as soundcloud_storage_id
from quantis.utils import app_paths

_INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_OUTTMPL_EXT = "%(ext)s"
# Те же форматы, что видят «Скачанные» и TrackManager.
_AUDIO_SUFFIXES = frozenset({".mp3", ".m4a"})
logger = logging.getLogger(__name__)


def _is_ready_file(file_path: Path) -> bool:
    try:
        return file_path.is_file() and file_path.stat().st_size > 0
    except OSError:
        return False


class PathProvider:
    """Пути к файлам трека. Каталоги берутся из ``app_paths``.

    Классовые атрибуты ниже — точка переопределения (тесты, плагины). Если они
    заданы, используются вместо каталогов пользователя.
    """

    MUSIC_FOLDER: str | None = None
    COVERS_FOLDER: str | None = None
    PLAYLISTS_FOLDER: str | None = None
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    @classmethod
    def music_folder(cls) -> str:
        return cls.MUSIC_FOLDER or str(app_paths.music_dir())

    @classmethod
    def covers_folder(cls) -> str:
        return cls.COVERS_FOLDER or str(app_paths.covers_dir())

    @classmethod
    def playlists_folder(cls) -> str:
        return cls.PLAYLISTS_FOLDER or str(app_paths.playlists_dir())

    @classmethod
    def ensure_storage_dirs(cls) -> None:
        for folder in (cls.music_folder(), cls.covers_folder(), cls.playlists_folder()):
            Path(folder).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_filename_part(value: str) -> str:
        cleaned = _INVALID_PATH_CHARS.sub("_", value.strip())
        cleaned = cleaned.replace("%", "_")
        while ".." in cleaned:
            cleaned = cleaned.replace("..", "_")
        cleaned = cleaned.strip(" .")
        return cleaned or "unknown"

    @classmethod
    def _sanitize_extension(cls, extension: str) -> str:
        raw = str(extension).lstrip(".")
        if raw == _OUTTMPL_EXT:
            return raw
        return cls._sanitize_filename_part(raw)

    def storage_id(self, track: Track) -> str:
        """Идентификатор в имени файла (SoundCloud — с префиксом sc)."""
        source = str(track.source).lower()
        if source == TrackSource.SOUNDCLOUD:
            return self._sanitize_filename_part(
                soundcloud_storage_id(track.track_id, source)
            )
        return self._sanitize_filename_part(str(track.track_id))

    def get_track_path(self, track: Track, extension: str | None = None) -> str:
        if extension is None:
            extension = str(getattr(track, "extension", "") or "mp3")
        title = self._sanitize_filename_part(track.title)
        author = self._sanitize_filename_part(track.author)
        ext = self._sanitize_extension(extension)
        return path.join(
            self.music_folder(),
            f"{self.storage_id(track)}_{title}_{author}.{ext}",
        )

    def find_track_file(self, track: Track) -> str | None:
        """Скачанный файл трека или None.

        Имя из title/author не всегда совпадает с файлом на диске: YouTube
        вычищает «Отметок Нравится» из автора, а файл назван ещё со статистикой.
        Поэтому запасной путь — поиск по id в начале имени.
        """
        exact = Path(self.get_track_path(track))
        if _is_ready_file(exact):
            return str(exact)
        music_dir = Path(self.music_folder())
        prefix = glob.escape(f"{self.storage_id(track)}_")
        try:
            candidates = sorted(music_dir.glob(f"{prefix}*"))
        except OSError:
            return None
        for candidate in candidates:
            if candidate.suffix.lower() in _AUDIO_SUFFIXES and _is_ready_file(
                candidate
            ):
                return str(candidate)
        return None

    def get_cover_path(self, track: Track, extension: str = "jpg") -> str:
        ext = self._sanitize_extension(extension)
        return path.join(self.covers_folder(), f"{self.storage_id(track)}.{ext}")

    def get_video_cache_path(self, track: Track, extension: str = "mp4") -> str:
        """Кэш видео для динамических обоев (не путать с аудио в music/)."""
        video_dir = path.join(self.music_folder(), ".video")
        Path(video_dir).mkdir(parents=True, exist_ok=True)
        ext = self._sanitize_extension(extension)
        return path.join(video_dir, f"{self.storage_id(track)}.{ext}")
