from pathlib import Path

from quantis.models.track import SoundCloudTrack, YandexTrack, YoutubeTrack
from quantis.services.soundcloud import parse_storage_id
from quantis.utils import app_paths


class TrackManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, music_dir: str | Path | None = None):
        # Папка осталась для совместимости вызовов; скачанность берётся из индекса.
        self.music_dir = Path(music_dir) if music_dir else app_paths.music_dir()

    def is_downloaded(self, track_id, source: str | None = None) -> bool:
        """Проверка, что трек скачан (по индексу библиотеки)."""
        from quantis.providers.library_index import LibraryIndex

        tid = str(track_id)
        normalized = (source or "").lower().strip()
        index = LibraryIndex.instance()
        if normalized in ("soundcloud", "sc"):
            return index.has("soundcloud", parse_storage_id(tid) or tid)
        if normalized in ("youtube", "yt"):
            return index.has("youtube", tid)
        if normalized in ("yandex", "ya"):
            return index.has("yandex", tid)
        # Источник неизвестен — ищем id в любом источнике.
        return index.has(None, tid)

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
