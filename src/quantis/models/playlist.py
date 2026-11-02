"""Модель плейлиста

Плейлисты пользователя - это плейлисты, которые создают пользователи.
Плейлисты системы - это плейлисты, которые создаются системой.

Плейлисты пользователя хранятся в файле playlists/user_playlists.json

Классы:
1. Playlist - абстрактный класс плейлиста
2. UserPlaylist - класс плейлиста пользователя
3. DownloadPlaylist - класс плейлиста системы
4. RecentlyPlayedPlaylist - системный плейлист недавно прослушанных
"""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Tuple

from quantis.models.track import SoundCloudTrack, Track, YandexTrack, YoutubeTrack
from quantis.providers import PathProvider, TrackManager
from quantis.types.upgrade_cycle import UpgradeCycle
from quantis.utils import get_asset_path

if TYPE_CHECKING:
    from quantis.providers.library_index import IndexEntry


class Playlist(ABC):
    def __init__(
        self, name: str, tracks: Iterable[Track], cover_path: str | None = None
    ) -> None:
        self.tracks = UpgradeCycle(tracks)
        self.name = name
        self.cover_path = cover_path

    def move_next_track(self) -> Track:
        """Переключаемся на следующий трек

        Returns:
            Track: следующий трек
        """
        return next(self.tracks)

    def move_previous_track(self) -> Track:
        """Переключаемся на предыдущий трек

        Returns:
            Track: предыдущий трек
        """
        return self.tracks.move_previous()

    def get_current_track(self) -> Track:
        """Получаем текущий трек

        Returns:
            Track: текущий трек
        """
        return self.tracks.peek_current()

    def get_track(self, index: int) -> Track:
        """Получаем трек по индексу

        Returns:
            Track: трек
        """
        return self.tracks.values[index]

    def delete_track(self, track: Track) -> bool:
        """Удаляем трек из плейлиста.

        Args:
            track (Track): трек для удаления

        Returns:
            bool: ``True`` если трек найден и удален, иначе ``False``.
        """
        return self.tracks.remove(track)

    def set_current_track(self, index: int) -> None:
        """Устанавливаем текущий трек плейлиста.

        Args:
            index (int): индекс (позиция) трека в плейлисте

        Returns:
            _type_: _description_
        """
        self.tracks.set_index(index)

    @staticmethod
    def load_playlist(playlist_path: str) -> tuple[str, list[Track], str | None]:
        """Загружаем плейлист из файла.

        Args:
            playlist_path (str): путь к файлу плейлиста

        Returns:
            tuple: название плейлиста и список треков
        """
        with open(playlist_path, encoding="utf-8") as file:
            playlist = json.load(file)
            name = str(playlist["name"])
            cover_path = playlist.get("cover_path", None)
            track_manager = TrackManager()
            tracks = [
                track_manager.get_track_from_playlist(
                    str(track["id"]),
                    track["title"],
                    track["author"],
                    source=track.get("source"),
                )
                for track in playlist["tracks"]
            ]
        return name, tracks, cover_path

    @abstractmethod
    def get_tracks(self) -> Tuple[Track, ...]:
        """Получаем список треков из плейлиста

        Returns:
            Tuple[Track]: список треков
        """
        pass

    def __len__(self) -> int:
        return len(self.tracks)

    def __str__(self) -> str:
        return f"{self.name} - {len(self.tracks)}"

    __repr__ = __str__


class RecommendationPlaylist(Playlist):
    """Плейлист рекомендаций: пачки с YouTube, очередь растёт в конце."""

    def __init__(
        self,
        name: str = "Рекомендации",
        tracks: Iterable[Track] | None = None,
        cover_path: str = get_asset_path("assets/icons/recomendation.svg"),
        *,
        seeds: Iterable[Track] | None = None,
        infinite: bool = False,
    ) -> None:
        super().__init__(name, tracks or (), cover_path)
        self.seeds = tuple(seeds or ())
        self._seed_index = 0
        self.infinite = infinite

    def get_tracks(self) -> Tuple[Track, ...]:
        """Получаем список треков из плейлиста

        Returns:
            Tuple[Track, ...]: список треков
        """
        return tuple(self.tracks.values)

    def append_tracks(self, tracks: Iterable[Track]) -> int:
        """Добавляет новые треки в конец (без дублей). Возвращает число добавленных."""
        existing = {(str(t.source), str(t.track_id)) for t in self.tracks.values}
        extra = [
            track
            for track in tracks
            if (str(track.source), str(track.track_id)) not in existing
        ]
        if not extra:
            return 0
        self.tracks.values = tuple(list(self.tracks.values) + extra)
        return len(extra)

    def take_seed(self, fallback: Track) -> Track:
        """Следующий сид из истории БД, иначе текущий трек."""
        if not self.seeds:
            return fallback
        seed = self.seeds[self._seed_index % len(self.seeds)]
        self._seed_index += 1
        return seed


class DownloadPlaylist(Playlist):
    """плейлист скачанных треков из music"""

    def __init__(
        self,
        name: str = "Скачанные",
        tracks: Iterable[Track] | None = None,
        cover_path: str = get_asset_path("assets/icons/download.svg"),
    ) -> None:
        super().__init__(name, tracks or (), cover_path)

    def get_tracks(self) -> Tuple[Track, ...]:
        """Получаем список треков из плейлиста

        Returns:
            Tuple[Track]: список треков
        """
        return tuple(self.tracks.values)

    def delete_track(self, track: Track) -> bool:
        from quantis.providers.library_index import LibraryIndex

        provider = PathProvider()
        index = LibraryIndex.instance()
        candidates: list[Path] = []
        indexed = index.path_for(str(track.source), str(track.track_id))
        if indexed is not None:
            candidates.append(indexed)
        # Точное имя `ID_Название_Автор` тоже попадает под префикс.
        candidates.extend(provider.legacy_candidates(track))
        seen: set[str] = set()
        for path in candidates:
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue  # файл остался — из индекса не убираем
            index.discard(path)
        super().delete_track(track)
        try:
            Path(provider.get_cover_path(track)).unlink(missing_ok=True)
        except OSError:
            pass
        track.downloaded = False
        return True

    @classmethod
    def get_playlist_from_path(cls, path_to_playlist: str) -> "DownloadPlaylist | None":
        """Получаем плейлист из файла

        Args:
            path_to_playlist (str): путь к файлу плейлиста

        Returns:
            DownloadPlaylist: плейлист
        """
        return DownloadPlaylist(
            name="Скачанные", tracks=cls.get_tracks_from_music_dir()
        )

    @staticmethod
    def get_tracks_from_music_dir() -> Tuple[Track, ...]:
        """Скачанные треки из индекса библиотеки (название и автор — из записи).

        Пока индекс не построен, список пуст: его обновит слушатель индекса.
        Два файла одного трека дают одну строку, файл с тегами важнее.
        """
        from quantis.providers.library_index import LibraryIndex

        chosen: dict[tuple[str, str], IndexEntry] = {}
        for entry in LibraryIndex.instance().entries():
            key = (entry.source, entry.track_id)
            current = chosen.get(key)
            if current is None or (entry.tagged and not current.tagged):
                chosen[key] = entry
        tracks: list[Track] = []
        for entry in chosen.values():
            track = _track_from_entry(entry)
            if track is not None:
                tracks.append(track)
        return tuple(tracks)


def _track_from_entry(entry: IndexEntry) -> Track | None:
    ext = entry.path.suffix.lstrip(".").lower()
    source = entry.source.lower()
    if source == "soundcloud":
        return SoundCloudTrack(
            track_id=entry.track_id,
            title=entry.title,
            author=entry.author,
            downloaded=True,
            extension=ext,
        )
    if source == "yandex":
        return YandexTrack(
            track_id=entry.track_id,
            title=entry.title,
            author=entry.author,
            downloaded=True,
        )
    if source == "youtube":
        return YoutubeTrack(
            track_id=entry.track_id,
            title=entry.title,
            author=entry.author,
            downloaded=True,
            extension=ext,
        )
    return None


class RecentlyPlayedPlaylist(Playlist):
    """Системный плейлист недавно прослушанных треков."""

    def __init__(
        self,
        name: str = "Недавно прослушанные",
        tracks: Iterable[Track] | None = None,
        cover_path: str = get_asset_path("assets/icons/recent.svg"),
    ) -> None:
        super().__init__(name, tracks or (), cover_path)

    def get_tracks(self) -> Tuple[Track, ...]:
        """Возвращает треки недавно прослушанного плейлиста."""
        return tuple(self.tracks.values)

    @classmethod
    def get_playlist_from_path(
        cls, path_to_playlist: str
    ) -> "RecentlyPlayedPlaylist | None":
        """Плейлист строится из БД, поэтому чтение с диска не используется."""
        return None


class LikedPlaylist(Playlist):
    """Системный плейлист любимых треков."""

    def __init__(
        self,
        name: str = "Любимые",
        tracks: Iterable[Track] | None = None,
        cover_path: str = get_asset_path("assets/icons/heart.svg"),
    ) -> None:
        super().__init__(name, tracks or (), cover_path)

    def get_tracks(self) -> Tuple[Track, ...]:
        return tuple(self.tracks.values)


class WavePlaylist(Playlist):
    """Моя волна — персональное радио (Yandex / позже YouTube)."""

    def __init__(
        self,
        name: str = "Моя волна",
        tracks: Iterable[Track] | None = None,
        cover_path: str = get_asset_path("assets/icons/radio.svg"),
        *,
        source: str = "yandex",
        seeds: Iterable[str] = ("user:onyourwave",),
        session_id: str | None = None,
        batch_id: str | None = None,
    ) -> None:
        super().__init__(name, tracks or (), cover_path)
        self.source = source
        # Сиды сессии: ``user:onyourwave``, ``mood:calm``, ``activity:run``…
        self.seeds: tuple[str, ...] = tuple(seeds)
        self.session_id = session_id
        self.batch_id = batch_id

    def get_tracks(self) -> Tuple[Track, ...]:
        return tuple(self.tracks.values)

    def append_tracks(self, tracks: Iterable[Track]) -> int:
        """Добавляет новые треки в конец (без дублей). Возвращает число добавленных."""
        existing = {str(t.track_id) for t in self.tracks.values}
        extra = [t for t in tracks if str(t.track_id) not in existing]
        if not extra:
            return 0
        self.tracks.values = tuple(list(self.tracks.values) + extra)
        return len(extra)


class UserPlaylist(Playlist):
    @classmethod
    def get_playlist_from_path(cls, path_to_playlist: str) -> "UserPlaylist | None":
        """Получаем плейлист из файла

        Args:
            path_to_playlist (str): путь к файлу плейлиста

        Returns:
            UserPlaylist: плейлист
        """
        if os.path.exists(path_to_playlist):
            return UserPlaylist(*cls.load_playlist(path_to_playlist))
        else:
            return None

    def get_tracks(self) -> Tuple[Track, ...]:
        """Получаем список треков из плейлиста

        Returns:
            Tuple[Track, ...]: список треков
        """
        return tuple(self.tracks.values)
