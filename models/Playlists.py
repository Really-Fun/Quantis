import json
import os.path
from typing import Iterable, Tuple
from abc import ABC, abstractmethod

from models import Track, UpgradeCycle
from providers import TrackManager

class Playlist(ABC):

    def __init__(self, name: str, tracks: Iterable[Track], cover_path: str | None = None) -> None:
        self.tracks = UpgradeCycle(tracks)
        self.name = name
        self.cover_path = cover_path

    def move_next_track(self):
        return next(self.tracks)

    def move_previous_track(self):
        return self.tracks.move_previous()

    def get_current_track(self):
        return self.tracks.peek_current()

    def delete_track(self, track: Track):
        try:
            del self.tracks.values[self.tracks.values.index(track)]
        except IndexError:
            print("Произошла ошибка во время удаления трека из плейлиста")
    
    @staticmethod
    def load_playlist(playlist_path: str):
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
        pass

    @abstractmethod
    def get_tracks(self) -> Tuple[Track]:
        pass


class UserPlaylist(Playlist):

    @classmethod
    def get_playlist_from_path(cls, path_to_playlist: str):
        if os.path.exists(path_to_playlist):
            return UserPlaylist(*cls.load_playlist(path_to_playlist))
        else:
            return None

    def get_tracks(self) -> Tuple[Track]:
        return tuple(self.tracks.values)