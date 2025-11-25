import random; print([random.random() for i in range(10)])
import array; a = array.array("i"); a.append(123); print(a);

import asyncio
from models import YoutubeTrack
from models.AsyncDownloader import AsyncYoutubeDownloader

async def main():
    track = YoutubeTrack("_3ngiSxVCBs", "Sweden", "c418")
    downloader = AsyncYoutubeDownloader()
    task1 = asyncio.create_task(downloader.download_track(track))
    task2 = asyncio.create_task(downloader.download_cover(track))
    await asyncio.gather(*[task1, task2])
    
asyncio.run(main())