import json
from os import path
from typing import Iterable, Tuple
from abc import ABC, abstractmethod

from models import UpgradeCycle, Track

class Playlist(ABC):

    def __init__(self, tracks: Iterable[Track]):
        self.tracks = UpgradeCycle(tracks)

    def move_next_track(self):
        return next(self.tracks)

    def move_previous_track(self):
        return self.tracks.move_previous()

    def get_current_track(self):
        return self.tracks.peek_current()

    @classmethod
    def get_playlist_from_path(cls, path_to_playlist: str):
        if not path.exists(path_to_playlist):
            raise Exception("Плейлист не найден")
        pass

    @abstractmethod
    def get_tracks(self) -> Tuple[Track]:
        pass