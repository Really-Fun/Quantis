from models import YandexTrack, YoutubeTrack
from pathlib import Path


class TrackManager:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, music_dir="music/"):
        self.music_dir = Path(music_dir)
        self._ids_cache = None

    @property
    def ids(self):
        if self._ids_cache is None:
            self._ids_cache = self._load_ids()
        return self._ids_cache

    def _load_ids(self):
        ids = set()
        if not self.music_dir.exists():
            return ids
        for track_file in self.music_dir.iterdir():
            if track_file.suffix in (".mp3", ".m4a"):
                track_id = track_file.stem.split("_")[0]
                ids.add(track_id)
        return ids

    def is_downloaded(self, track_id):
        return track_id in self.ids

    def get_track_from_playlist(self, track_id: str, title: str, author: str) -> YandexTrack | YoutubeTrack:
        """Получаем трек по его id, названию и автору

        Args:
            track_id (str): id трека
            title (str): название трека
            author (str): автор трека

        Returns:
            YandexTrack | YoutubeTrack: трек
        """
        if track_id.isdigit():
            return YandexTrack(
                track_id=int(track_id),
                title=title,
                author=author,
                downloaded=self.is_downloaded(track_id),
            )
        else:
            return YoutubeTrack(
                track_id=track_id,
                title=title,
                author=author,
                downloaded=self.is_downloaded(track_id),
            )