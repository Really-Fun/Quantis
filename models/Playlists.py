"""Модель плейлиста

Плейлисты могут быть двух типов:
1. Плейлисты пользователя
2. Плейлисты системы

Плейлисты пользователя - это плейлисты, которые создают пользователи.
Плейлисты системы - это плейлисты, которые создаются системой.

Плейлисты пользователя хранятся в файле playlists/user_playlists.json

Классы:
1. Playlist - абстрактный класс плейлиста
2. UserPlaylist - класс плейлиста пользователя
3. DownloadPlaylist - класс плейлиста системы
4. RecentlyPlayedPlaylist - системный плейлист недавно прослушанных
"""

import json
import os
import os.path
from typing import Iterable, Tuple
from abc import ABC, abstractmethod

from models import Track, YandexTrack, YoutubeTrack, UpgradeCycle
from providers import TrackManager

class Playlist(ABC):

    def __init__(self, name: str, tracks: Iterable[Track], cover_path: str | None = None) -> None:
        self.tracks = UpgradeCycle(tracks)
        self.name = name
        self.cover_path = cover_path

    def move_next_track(self):
        """Переключаемся на следующий трек

        Returns:
            Track: следующий трек
        """
        return next(self.tracks)

    def move_previous_track(self):
        """Переключаемся на предыдущий трек

        Returns:
            Track: предыдущий трек
        """
        return self.tracks.move_previous()

    def get_current_track(self):
        """Получаем текущий трек

        Returns:
            Track: текущий трек
        """
        return self.tracks.peek_current()

    def delete_track(self, track: Track) -> bool:
        """Удаляем трек из плейлиста.

        Args:
            track (Track): трек для удаления

        Returns:
            bool: ``True`` если трек найден и удален, иначе ``False``.
        """
        try:
            del self.tracks.values[self.tracks.values.index(track)]
            return True
        except ValueError:
            return False
    
    @staticmethod
    def load_playlist(playlist_path: str):
        """Загружаем плейлист из файла

        Args:
            playlist_path (str): путь к файлу плейлиста

        Returns:
            tuple: название плейлиста и список треков
        """
        with open(playlist_path, encoding="utf-8", mode="r") as file:
            playlist = json.load(file)
            name = playlist["name"]
            track_manager = TrackManager()
            tracks = [
                track_manager.get_track_from_playlist(*(track["id"], track["title"], track["author"])) for track in playlist["tracks"]
            ]
        return name, tracks


    @classmethod
    @abstractmethod
    def get_playlist_from_path(cls, path_to_playlist: str):
        """Получаем плейлист из файла

        Args:
            path_to_playlist (str): путь к файлу плейлиста

        Returns:
            Playlist: плейлист
        """
        pass

    @abstractmethod
    def get_tracks(self) -> Tuple[Track]:
        """Получаем список треков из плейлиста

        Returns:
            Tuple[Track]: список треков
        """
        pass


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

    def get_tracks(self) -> Tuple[Track]:
        """Получаем список треков из плейлиста

        Returns:
            Tuple[Track]: список треков
        """
        return tuple(self.tracks.values)


class DownloadPlaylist(Playlist):
    """плейлист скачанных треков из music """

    def __init__(self, name: str = "Скачанные", tracks: Iterable[Track] | None = None, cover_path: str  = "playlist_covers/download.png") -> None:
        super().__init__(name, tracks or (), cover_path)

    def get_tracks(self) -> Tuple[Track]:
        """Получаем список треков из плейлиста

        Returns:
            Tuple[Track]: список треков
        """
        return tuple(self.tracks.values)

    @classmethod
    def get_playlist_from_path(cls, path_to_playlist: str) -> "DownloadPlaylist | None":
        """Получаем плейлист из файла

        Args:
            path_to_playlist (str): путь к файлу плейлиста

        Returns:
            DownloadPlaylist: плейлист
        """
        return DownloadPlaylist(name="Скачанные", tracks=cls.get_tracks_from_music_dir())

    @staticmethod
    def get_tracks_from_music_dir() -> Tuple[Track]:
        """Получаем список треков из директории music

        Returns:
            Tuple[Track]: список треков
        """
        music_dir = "music"
        if not os.path.isdir(music_dir):
            return ()
        tracks = []
        for track_file in os.listdir(music_dir):
            try:
                name, ext = os.path.splitext(track_file)
                parts = name.split("_", 2)
                if len(parts) < 3:
                    continue
                track_id, track_title, track_author = parts
                if ext == ".mp3":
                    tracks.append(YandexTrack(track_id=track_id, title=track_title, author=track_author, downloaded=True))
                elif ext == ".m4a":
                    tracks.append(YoutubeTrack(track_id=track_id, title=track_title, author=track_author, downloaded=True))
            except Exception:
                continue
        return tuple(tracks)


class RecentlyPlayedPlaylist(Playlist):
    """Системный плейлист недавно прослушанных треков."""

    def __init__(
        self,
        name: str = "Недавно прослушанные",
        tracks: Iterable[Track] | None = None,
        cover_path: str = "playlist_covers/heart.png",
    ) -> None:
        super().__init__(name, tracks or (), cover_path)

    def get_tracks(self) -> Tuple[Track]:
        """Возвращает треки недавно прослушанного плейлиста."""
        return tuple(self.tracks.values)

    @classmethod
    def get_playlist_from_path(cls, path_to_playlist: str) -> "RecentlyPlayedPlaylist | None":
        """Плейлист строится из БД, поэтому чтение с диска не используется."""
        return None