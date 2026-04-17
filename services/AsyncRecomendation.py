from abc import ABC
from concurrent.futures import ThreadPoolExecutor
import asyncio

from ytmusicapi import YTMusic

from models import Track, YandexTrack, YoutubeTrack, RecomendationPlaylist
from config import GetClients
from .AsyncFinder import AsyncYoutubeFinder


class AsyncRecomendation:
    def __init__(self):
        self.client: YTMusic = GetClients().get_youtube_client()
        self.finder: AsyncYoutubeFinder = AsyncYoutubeFinder()

    async def generate_radio_from_track(self, track: Track):
        video_id = track.track_id
        if not isinstance(track, YoutubeTrack):
            video_id = await self.get_id_if_not_yt(track)

        with ThreadPoolExecutor() as thread:
            result = await asyncio.get_running_loop().run_in_executor(
                thread,
                lambda: self.client.get_watch_playlist(videoId=video_id, limit=10),
            )

        tracks = []
        for track_info in result.get("tracks", []):
            tracks.append(
                YoutubeTrack(
                    track_id=track_info["videoId"],
                    title=track_info["title"],
                    author=", ".join(
                        [a["name"] for a in track_info.get("artists", [])]
                    ),
                    downloaded=False,
                )
            )

        return RecomendationPlaylist(name=track.title + track.author, tracks=tracks)

    async def get_id_if_not_yt(self, track: Track) -> str:
        result_id = await self.finder.get_tracks(
            track.title + " " + track.author, value=1
        )
        return result_id[0].track_id
