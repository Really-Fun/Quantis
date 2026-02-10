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
"""

import json
from os import path
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

    def delete_track(self, track: Track):
        """Удаляем трек из плейлиста

        Args:
            track (Track): трек для удаления
        """
        try:
            del self.tracks.values[self.tracks.values.index(track)]
        except ValueError:
            print("Произошла ошибка во время удаления трека из плейлиста")
    
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

    def __init__(self, name: str = "Downloaded Tracks", tracks: Iterable[Track] = None, cover_path: str | None = None) -> None:
        super().__init__(name, tracks, cover_path)

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
        return DownloadPlaylist(name="Downloaded Tracks", tracks=cls.get_tracks_from_music_dir())

    @staticmethod
    def get_tracks_from_music_dir() -> Tuple[Track]:
        """Получаем список треков из директории music

        Returns:
            Tuple[Track]: список треков
        """
        tracks = []
        for track_file in path.listdir("music"):
            if track_file.endswith(".mp3"):
                track_id, track_title, track_author = track_file.split("_")
                tracks.append(YandexTrack(track_id=track_id, title=track_title, author=track_author))
            elif track_file.endswith(".m4a"):
                track_id, track_title, track_author = track_file.split("_")
                tracks.append(YoutubeTrack(track_id=track_id, title=track_title, author=track_author))
        return tracks