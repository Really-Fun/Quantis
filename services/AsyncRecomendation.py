from abc import ABC

from yandex_music import ClientAsync

from models import Track, YandexTrack, YoutubeTrack, RecomendationPlaylist
from config import GetClients


class AsyncRecomendation:

    def __init__(self):
        self.client: ClientAsync = GetClients().get_yandex_client()

    async def get_personal_playlist(self) -> RecomendationPlaylist:
        playlist_data = await client.feed()

        playlists = []
        for playlist in playlist_data.generated_playlists:
            p_info = {
                "title": playlist.data.title,
                "type": playlist.type,
                "track_count": playlist.data.track_count,
                "id": f"{playlist.data.owner.uid}:{playlist.data.kind}",
            }
            playlists.append(p_info)

        test = await client.playlists_list(playlists[0]["id"])
        tracks = await test[0].fetch_tracks_async()
        result_tracks = []
        for track in tracks:
            result_tracks.append(
                YandexTrack(
                    track["track"]["id"],
                    track["track"]["title"],
                    track["track"]["artists"][0]["name"],
                )
            )
        return RecomendationPlaylist(tracks=result_tracks)
