from os import path
from models import YandexTrack, YoutubeTrack


class PathProvider:
    MUSIC_FOLDER = "music/"
    COVERS_FOLDER = "covers/"

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls, *args, **kwargs)
        return cls.instance

    def get_track_path(self, track: YandexTrack | YoutubeTrack, extension: str = "mp3") -> str:
        return path.join(self.MUSIC_FOLDER, f"{track.track_id}_{track.title}_{track.author}.{extension}")
    
    def get_cover_path(self, track: YandexTrack | YoutubeTrack, extension: str = "jpg") -> str:
        return path.join(self.COVERS_FOLDER, f"{track.track_id}.{extension}")