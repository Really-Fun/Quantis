from asyncio import run
from yandex_music import ClientAsync

from config import GetClients


async def main():
    client = ClientAsync(
        "y0_AgAAAABVCDf8AAG8XgAAAAEPbydYAABxT-2rrGdJOpLbDEsGSLWwbelvrg"
    )
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

    test = await client.playlists_list(playlists[1]["id"])
    tracks = await test[0].fetch_tracks_async()
    result_tracks = []
    for track in tracks:
        print(track["track"]["title"])


if __name__ == "__main__":
    run(main=main())
