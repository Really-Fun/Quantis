"""Индекс скачанных файлов: какой файл принадлежит (source, track_id).

Источник истины для воспроизведения, удаления и списка «Скачанные». Личность
файла берётся из встроенных тегов; файлы старого формата `ID_Название_Автор`
разбираются по имени. Результат кэшируется на диске, чтобы при запуске не
читать теги всех файлов заново.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from quantis.providers.legacy_names import parse_legacy_names
from quantis.services.track_tags import read_identity
from quantis.utils import app_paths

logger = logging.getLogger(__name__)

_AUDIO_SUFFIXES = frozenset({".mp3", ".m4a"})
_CACHE_VERSION = 1
_SOUNDCLOUD_PREFIX = "sc"

Key = tuple[str, str]


@dataclass(frozen=True)
class IndexEntry:
    source: str
    track_id: str
    title: str
    author: str
    path: Path
    tagged: bool
    # Имя файла читается и как yandex, и как youtube; запись — yandex-прочтение.
    ambiguous: bool = False


@dataclass(frozen=True)
class _Record:
    """Результат разбора одного файла (то, что хранится в кэше)."""

    size: int
    mtime_ns: int
    source: str
    track_id: str
    title: str
    author: str
    tagged: bool
    ambiguous: bool = False
    alias_source: str = ""
    alias_track_id: str = ""


def _key(source: str | None, track_id: str) -> Key:
    src = str(source).lower() if source is not None else ""
    tid = str(track_id)
    if src == "soundcloud" and tid.startswith(_SOUNDCLOUD_PREFIX):
        tid = tid[len(_SOUNDCLOUD_PREFIX):]
    return src, tid


class LibraryIndex:
    """Индекс «(источник, id) -> файл» для папки с музыкой."""

    # Точки переопределения (тесты): пути по умолчанию иначе берутся лениво.
    CACHE_PATH: Path | None = None
    _instance: LibraryIndex | None = None

    def __init__(
        self, music_dir: Path | None = None, cache_path: Path | None = None
    ) -> None:
        self._music_dir = Path(music_dir) if music_dir is not None else None
        self._cache_path = Path(cache_path) if cache_path is not None else None
        self._lock = threading.Lock()
        self._files: dict[str, _Record] = {}
        self._files_dir: Path | None = None  # папка, к которой относятся _files
        self._keys: dict[Key, str] = {}
        self._ready = False
        self._event: asyncio.Event | None = None
        self._listeners: list[Callable[[], None]] = []

    # --- синглтон ---

    @classmethod
    def instance(cls) -> LibraryIndex:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # --- пути ---

    @property
    def music_dir(self) -> Path:
        """Папка музыки; без явного значения берётся актуальная у PathProvider."""
        if self._music_dir is not None:
            return self._music_dir
        # Импорт здесь: providers <-> models имеют циклическую зависимость.
        from quantis.providers.path_provider import PathProvider

        return Path(PathProvider.music_folder())

    @property
    def cache_path(self) -> Path:
        if self._cache_path is not None:
            return self._cache_path
        return self.CACHE_PATH or app_paths.data_dir() / "library_index.json"

    @property
    def is_ready(self) -> bool:
        return self._ready

    # --- кэш ---

    def load_cached(self) -> None:
        """Синхронно читает кэш. Чужая папка или битый файл дают пустой индекс."""
        music_dir = self.music_dir
        files = self._read_cache(music_dir)
        with self._lock:
            self._files = files
            self._files_dir = music_dir
            self._rebuild_keys(music_dir)

    def _read_cache(self, music_dir: Path) -> dict[str, _Record]:
        try:
            data = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if data["version"] != _CACHE_VERSION or data["music_dir"] != str(music_dir):
                return {}
            raw = data["files"]
            if not isinstance(raw, dict):
                return {}
            return {name: _Record(**fields) for name, fields in raw.items()}
        except (OSError, ValueError, KeyError, TypeError):
            return {}

    def _save_cache(self, music_dir: Path, files: dict[str, _Record]) -> None:
        data = {
            "version": _CACHE_VERSION,
            "music_dir": str(music_dir),
            "files": {name: rec.__dict__ for name, rec in files.items()},
        }
        target = self.cache_path
        part = target.with_name(target.name + ".part")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            part.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            os.replace(part, target)
        except OSError:
            logger.warning("Не удалось сохранить кэш индекса %s", target, exc_info=True)

    # --- разбор файлов ---

    @staticmethod
    def _analyze(path: Path, size: int, mtime_ns: int) -> _Record | None:
        identity = read_identity(path)
        if identity is not None:
            return _Record(
                size, mtime_ns, identity.source, identity.track_id,
                identity.title, identity.artist, True,
            )
        readings = parse_legacy_names(path.name)
        if not readings:
            return None
        main = readings[0]
        alias = readings[1] if len(readings) > 1 else None
        return _Record(
            size, mtime_ns, main.source, main.track_id, main.title, main.author,
            False,
            ambiguous=alias is not None,
            alias_source=alias.source if alias else "",
            alias_track_id=alias.track_id if alias else "",
        )

    def _rebuild_keys(self, music_dir: Path) -> None:
        """Пересобирает ключи; вызывать под блокировкой.

        Приоритет при совпадении ключа: файл с тегами, затем основное
        прочтение, затем алиас.
        """
        best: dict[Key, tuple[tuple[bool, bool], str]] = {}
        for name, rec in self._files.items():
            candidates = [(_key(rec.source, rec.track_id), (rec.tagged, True))]
            if rec.ambiguous and rec.alias_source:
                candidates.append(
                    (_key(rec.alias_source, rec.alias_track_id), (rec.tagged, False))
                )
            for key, rank in candidates:
                current = best.get(key)
                if current is None or rank > current[0]:
                    best[key] = (rank, name)
        self._keys = {key: name for key, (_, name) in best.items()}

    def _entry(self, name: str, music_dir: Path) -> IndexEntry:
        rec = self._files[name]
        return IndexEntry(
            rec.source, rec.track_id, rec.title, rec.author,
            music_dir / name, rec.tagged, rec.ambiguous,
        )

    # --- обновление ---

    def _scan(self, music_dir: Path) -> None:
        """Полный проход по папке (рабочий поток)."""
        with self._lock:
            old = dict(self._files) if self._files_dir == music_dir else {}
        new: dict[str, _Record] = {}
        try:
            with os.scandir(music_dir) as it:
                for item in it:
                    if os.path.splitext(item.name)[1].lower() not in _AUDIO_SUFFIXES:
                        continue
                    try:
                        if not item.is_file():
                            continue
                        st = item.stat()
                    except OSError:
                        continue
                    prev = old.get(item.name)
                    if prev and prev.size == st.st_size and prev.mtime_ns == st.st_mtime_ns:
                        new[item.name] = prev
                        continue
                    rec = self._analyze(Path(item.path), st.st_size, st.st_mtime_ns)
                    if rec is not None:
                        new[item.name] = rec
        except OSError:
            logger.warning("Не удалось прочитать папку %s", music_dir, exc_info=True)
        with self._lock:
            self._files = new
            self._files_dir = music_dir
            self._rebuild_keys(music_dir)
        self._save_cache(music_dir, new)
        self._ready = True
        for callback in list(self._listeners):
            try:
                callback()
            except Exception:
                logger.exception("Ошибка слушателя индекса")

    async def refresh(self) -> None:
        """Пересканирует папку в рабочем потоке; читает теги только у изменившихся."""
        music_dir = self.music_dir
        await asyncio.to_thread(self._scan, music_dir)
        if self._event is None:
            self._event = asyncio.Event()
        self._event.set()

    async def wait_ready(self) -> None:
        if self._ready:
            return
        if self._event is None:
            self._event = asyncio.Event()
        await self._event.wait()

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Слушатель вызывается из рабочего потока после `refresh`."""
        self._listeners.append(callback)

    def reset(self) -> None:
        """Очищает индекс (смена папки); он снова не готов."""
        with self._lock:
            self._files = {}
            self._files_dir = None
            self._keys = {}
        self._ready = False
        self._event = None

    # --- запросы ---

    def _lookup(self, key: Key) -> IndexEntry | None:
        music_dir = self.music_dir
        with self._lock:
            name = self._keys.get(key)
            if name is None or self._files_dir != music_dir:
                return None
            entry = self._entry(name, music_dir)
        if entry.path.is_file():
            return entry
        self._drop(name)
        return None

    def _drop(self, name: str) -> None:
        with self._lock:
            if self._files.pop(name, None) is None:
                return
            music_dir = self._files_dir or self.music_dir
            self._rebuild_keys(music_dir)
            files = dict(self._files)
        self._save_cache(music_dir, files)

    def entry_for(self, source: str, track_id: str) -> IndexEntry | None:
        return self._lookup(_key(source, track_id))

    def path_for(self, source: str, track_id: str) -> Path | None:
        entry = self._lookup(_key(source, track_id))
        return entry.path if entry else None

    def has(self, source: str | None, track_id: str) -> bool:
        if source is not None:
            return self._lookup(_key(source, track_id)) is not None
        with self._lock:
            keys = list(self._keys)
        tid = str(track_id)
        wanted = {tid, _key("soundcloud", tid)[1]}
        return any(
            self._lookup(key) is not None for key in keys if key[1] in wanted
        )

    def entries(self) -> list[IndexEntry]:
        music_dir = self.music_dir
        with self._lock:
            if self._files_dir != music_dir:
                return []
            result = [self._entry(name, music_dir) for name in self._files]
        return result

    # --- точечные изменения ---

    def put(self, path: Path) -> IndexEntry | None:
        """Индексирует один файл (после скачивания или переименования)."""
        path = Path(path)
        music_dir = self.music_dir
        try:
            if path.parent.resolve() != music_dir.resolve():
                return None
            st = path.stat()
        except OSError:
            return None
        if path.suffix.lower() not in _AUDIO_SUFFIXES:
            return None
        rec = self._analyze(path, st.st_size, st.st_mtime_ns)
        with self._lock:
            if self._files_dir != music_dir:
                self._files = {}
                self._files_dir = music_dir
            if rec is None:
                self._files.pop(path.name, None)
            else:
                self._files[path.name] = rec
            self._rebuild_keys(music_dir)
            files = dict(self._files)
            entry = self._entry(path.name, music_dir) if rec else None
        self._save_cache(music_dir, files)
        return entry

    def discard(self, path: Path) -> None:
        self._drop(Path(path).name)
