"""Скачанные треки: файлы в папке приложения и их каталог.

Файлы лежат в <AppDataLocation>/offline (на Android — внутренняя память
приложения, система её не чистит, в отличие от кэша), каталог — index.json
там же. Каталог меняется только из потока интерфейса; download() — блокирующая,
её зовут из пула потоков: качает во временный файл и переименовывает.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from dataclasses import asdict
from pathlib import Path

import art
import sources
from PySide6.QtCore import QStandardPaths
from sources import YANDEX, Result

log = logging.getLogger(__name__)
_TIMEOUT = 30
_CHUNK = 256 * 1024
# Кодек Яндекса → расширение файла (MediaPlayer Android смотрит на содержимое,
# но расширение помогает при определении типа).
_EXT = {"mp3": "mp3", "aac": "m4a", "he-aac": "m4a", "mp4": "m4a", "flac": "flac"}


def _key(result: Result) -> str:
    return f"{result.source}:{result.track_id}"


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in text)


class OfflineStore:
    def __init__(self, root: Path | None = None) -> None:
        if root is None:
            base = QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
            root = Path(base or Path.home() / ".quantis-mobile") / "offline"
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._entries: dict[str, dict] = self._load()

    # --- каталог ----------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        try:
            raw = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        entries = {}
        for item in raw if isinstance(raw, list) else []:
            try:
                result = Result(**item["track"])
            except (KeyError, TypeError):
                continue
            if (self.root / str(item.get("file", ""))).is_file():
                entries[_key(result)] = item
        return entries

    def _save(self) -> None:
        tmp = self._index_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(list(self._entries.values()), ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, self._index_path)

    def tracks(self) -> list[Result]:
        """Скачанное, новое — первым."""
        return [Result(**e["track"]) for e in reversed(list(self._entries.values()))]

    def has(self, result: Result) -> bool:
        return _key(result) in self._entries

    def path(self, result: Result) -> Path | None:
        entry = self._entries.get(_key(result))
        if entry is None:
            return None
        path = self.root / entry["file"]
        return path if path.is_file() else None

    def total_bytes(self) -> int:
        return sum(int(e.get("size", 0)) for e in self._entries.values())

    def add(self, result: Result, file_name: str) -> None:
        size = (self.root / file_name).stat().st_size
        self._entries.pop(_key(result), None)  # в конец: новое — первым в tracks()
        self._entries[_key(result)] = {
            "track": asdict(result),
            "file": file_name,
            "size": size,
        }
        self._save()

    def remove(self, result: Result) -> None:
        entry = self._entries.pop(_key(result), None)
        if entry is None:
            return
        (self.root / entry["file"]).unlink(missing_ok=True)
        self._save()

    # --- скачивание (из пула потоков) -------------------------------------

    def download(self, result: Result, token: str) -> str:
        """Скачать трек; вернуть имя файла в root. Обложку — в кэш заодно."""
        base = f"{result.source}_{_safe(result.track_id)}"
        if result.source == YANDEX:
            name = self._download_yandex(result, token, base)
        else:
            name = self._download_youtube(result, base)
        art.load_cover(result.cover)  # чтобы обложка была и без сети
        return name

    def _download_yandex(self, result: Result, token: str, base: str) -> str:
        url, codec = sources.yandex_link(token, result.track_id)
        name = f"{base}.{_EXT.get(codec, 'mp3')}"
        tmp = self.root / (name + ".part")
        request = urllib.request.Request(url, headers={"User-Agent": "Quantis"})
        try:
            with (
                urllib.request.urlopen(
                    request, timeout=_TIMEOUT, context=art._ssl_context()
                ) as response,
                open(tmp, "wb") as out,
            ):
                while chunk := response.read(_CHUNK):
                    out.write(chunk)
            os.replace(tmp, self.root / name)
        finally:
            tmp.unlink(missing_ok=True)
        return name

    def _download_youtube(self, result: Result, base: str) -> str:
        import yt_dlp

        error: Exception | None = None
        for opts in sources.youtube_download_options(str(self.root / f"{base}.%(ext)s")):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(
                        f"https://www.youtube.com/watch?v={result.track_id}", download=True
                    )
                    path = Path(ydl.prepare_filename(info))
            except Exception as exc:
                error = exc
                continue
            if path.is_file():
                return path.name
        raise RuntimeError(f"YouTube не отдал файл: {error}")
