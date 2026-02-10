"""
Асинхронный поиск треков по платформам:
Yandex
Youtube
"""

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from asyncio import get_running_loop

import yandex_music.exceptions

from models import Track, YandexTrack, YoutubeTrack
from config import GetClients


class AsyncFinderInterface(ABC):

    @abstractmethod
    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        ...

    @abstractmethod
    async def get_track(self, id: int) -> Track | None:
        ...


class AsyncYandexFinder(AsyncFinderInterface):

    def __init__(self):
        self.client = GetClients().get_yandex_client()

    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        try:
            tracks = await self.client.search(title)
            return [YandexTrack(
                                track["id"],
                                track["title"],
                                " & ".join(artist["name"] for artist in track["artists"]),
                                downloaded=False
                                )
                    for track in tracks["tracks"]["results"]]
        except yandex_music.exceptions.NetworkError:
            #TODO logger
            return []
        except yandex_music.exceptions.YandexMusicError:
            return []

    async def get_track(self, id: int) -> Track | None:
        try:
            track_info = await self.client.tracks(id)
            track = track_info[0]
            return YandexTrack(
                                track["id"],
                                track["title"],
                                " & ".join(artist["name"] for artist in track["artists"]),
                                downloaded=False
                                )
        except yandex_music.exceptions.YandexMusicError:
            #TODO legger
            return None


class AsyncYoutubeFinder(AsyncFinderInterface):

    def __init__(self) -> None:
        self.client = GetClients().get_youtube_client()

    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        with ThreadPoolExecutor() as pool:
            loop = get_running_loop()
            tracks = await loop.run_in_executor(pool, self.sync_get_tracks, title, value)
        return tracks

    async def get_track(self, id: int) -> Track | None:
        with ThreadPoolExecutor() as pool:
            loop = get_running_loop()
            track = await loop.run_in_executor(pool, self.sync_get_track, id)
        return track

    def sync_get_tracks(self, title: str, value: int = 5) -> list[Track]:
        results = self.client.search(query=title, filter="songs", limit=value)
        tracks = []
        for track in results:
            track_id = track.get("videoId")
            track_title = track.get("title")
            authors = " | ".join([author["name"] for author in track["artists"]])
            tracks.append(
                YoutubeTrack(
                    track_id=track_id,
                    title=track_title,
                    author=authors,
                    downloaded=False
                )
            )
        return tracks

    def sync_get_track(self, id: int) -> Track | None:
        results = self.client.get_song(id)
        if not results:
            return None
        track_id = results.get("videoId") or id
        track_title = results.get("title", "")
        authors = " | ".join([author["name"] for author in results.get("artists", [])])
        return YoutubeTrack(track_id=track_id, title=track_title, author=authors, downloaded=False)


class AsyncFinder(AsyncFinderInterface):

    def __init__(self):
        self._yandex_finder = AsyncYandexFinder()
        self._youtube_finder = AsyncYoutubeFinder()

    async def get_tracks(self, title: str, value: int = 5) -> list[Track]:
        yandex_tracks = await self._yandex_finder.get_tracks(title, value)
        youtube_tracks = await self._youtube_finder.get_tracks(title, value)
        return yandex_tracks + youtube_tracks

    async def get_track(self, id: int) -> Track:
        yandex_track = await self._yandex_finder.get_track(id)
        if yandex_track is not None:
            return yandex_track
        return await self._youtube_finder.get_track(id)