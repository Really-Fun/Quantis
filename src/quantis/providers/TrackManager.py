from pathlib import Path
from typing import List

from quantis.models.track import SoundCloudTrack, YandexTrack, YoutubeTrack
from quantis.services.soundcloud import parse_storage_id
from quantis.services.soundcloud import storage_id as soundcloud_storage_id
from quantis.utils import app_paths


class TrackManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, music_dir: str | Path | None = None):
        self.music_dir = Path(music_dir) if music_dir else app_paths.music_dir()
        self._ids_cache = None

    @property
    def ids(self) -> List[str]:
        """Свойство возвращает список треков

        Returns:
            List[str]: _description_
        """
        if self._ids_cache is None:
            self._ids_cache = self._load_ids()
        return self._ids_cache

    def _load_ids(self) -> List[str]:
        """Загрузка айди треков, содержащихся в папке music/
        для применения данных в логике программы

        Returns:
            List[str]: Список айди треков
        """
        ids = set()
        if not self.music_dir.exists():
            return ids
        for track_file in self.music_dir.iterdir():
            if track_file.suffix in (".mp3", ".m4a"):
                track_id = track_file.stem.split("_")[0]
                ids.add(track_id)
        return ids

    def is_downloaded(self, track_id, source: str | None = None) -> bool:
        """Проверка, что трек скачан."""
        tid = str(track_id)
        if (source or "").lower() == "soundcloud":
            return soundcloud_storage_id(tid) in self.ids or tid in self.ids
        return tid in self.ids

    def get_track_from_playlist(
        self,
        track_id: str,
        title: str,
        author: str,
        source: str | None = None,
    ) -> YandexTrack | YoutubeTrack | SoundCloudTrack:
        """Получаем трек по id / названию / автору (и опционально source)."""
        normalized_source = (source or "").lower().strip()
        downloaded = self.is_downloaded(str(track_id), source=normalized_source or None)
        if normalized_source in ("soundcloud", "sc"):
            numeric = parse_storage_id(str(track_id)) or track_id
            return SoundCloudTrack(
                track_id=numeric,
                title=title,
                author=author,
                downloaded=downloaded,
            )
        if normalized_source in ("youtube", "yt"):
            return YoutubeTrack(
                track_id=track_id,
                title=title,
                author=author,
                downloaded=downloaded,
            )
        if normalized_source in ("yandex", "ya") or str(track_id).isdigit():
            return YandexTrack(
                track_id=int(track_id) if str(track_id).isdigit() else track_id,
                title=title,
                author=author,
                downloaded=downloaded,
            )
        return YoutubeTrack(
            track_id=track_id,
            title=title,
            author=author,
            downloaded=downloaded,
        )
