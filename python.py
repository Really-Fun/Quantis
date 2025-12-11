# import asyncio
# import time
# from asyncio import gather
#
# import colorama
#
# from models import YoutubeTrack, YandexTrack
# from services.AsyncDownloader import AsyncYoutubeDownloader, AsyncYandexDownloader
#
# downloader = AsyncYoutubeDownloader()
# downloader_yandex = AsyncYandexDownloader()
#
# async def yandex_url():
#     start = time.time()
#     track = YandexTrack(12554, "Тест", "Тест")
#     print(colorama.Fore.RED + "Запуск асинхронного получения потоковой ссылки на трек с Yandex:")
#     await asyncio.create_task(downloader_yandex.get_stream_url(track))
#     end = time.time()
#     print(colorama.Fore.RED + "Получен яндекс трек за:" + str(end - start))
#
# async def yandex_cover():
#     start = time.time()
#     track = YandexTrack(12554, "Тест", "Тест")
#     print(colorama.Fore.RED + "Запуск асинхронного получения обложки на трек с Yandex:")
#     await asyncio.create_task(downloader_yandex.download_cover(track))
#     end = time.time()
#     print(colorama.Fore.RED + "Получена обложка с яндекса за:" + str(end - start))
#
# async def youtube_url():
#     start = time.time()
#     track = YoutubeTrack("_3ngiSxVCBs", "Sweden", "c418")
#     print(colorama.Fore.CYAN + "Запуск асинхронного получения трека с Youtube:")
#     await asyncio.create_task(downloader.get_stream_url(track))
#     end = time.time()
#     print(colorama.Fore.CYAN + "Получен трек с ютуба за:" + str(end - start))
#
# async def youtube_cover():
#     start = time.time()
#     track = YoutubeTrack("_3ngiSxVCBs", "Sweden", "c418")
#     print(colorama.Fore.CYAN + "Запуск асинхронного получения трека с Youtube:")
#     await asyncio.create_task(downloader.download_cover(track))
#     end = time.time()
#     print(colorama.Fore.CYAN + "Получена обложка с ютуба за:" + str(end - start))
#
#
# async def main():
#     for task in [yandex_url(), yandex_cover(), youtube_cover(), youtube_url()]:
#         await task
#
# asyncio.run(main())

from  services import AsyncFinder
import asyncio

a = AsyncFinder()

async def main():
    tracks = await a.get_tracks("miyagi", 5)
    print(tracks)

asyncio.run(main())