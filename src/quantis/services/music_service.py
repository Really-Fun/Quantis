from __future__ import annotations

from quantis.providers import PathProvider


class MusicService:
    """Фасад над finder/streamer/downloader — тяжёлые части создаются лениво."""

    def __init__(
        self,
        finder=None,
        streamer=None,
        downloader=None,
        provider: PathProvider | None = None,
    ) -> None:
        self._finder = finder
        self._streamer = streamer
        self._downloader = downloader
        self._provider = provider or PathProvider()
        self._recommendation = None
        self._wave = None

    @property
    def downloader(self):
        if self._downloader is None:
            from quantis.services.async_downloader import AsyncDownloader

            self._downloader = AsyncDownloader()
        return self._downloader

    @property
    def finder(self):
        if self._finder is None:
            from quantis.services.async_finder import AsyncFinder

            self._finder = AsyncFinder()
        return self._finder

    @property
    def recommendation(self):
        if self._recommendation is None:
            from quantis.services.async_recommendation import AsyncRecommendation

            self._recommendation = AsyncRecommendation(self.finder.youtube)
        return self._recommendation

    @property
    def wave(self):
        if self._wave is None:
            from quantis.services.async_wave import AsyncWaveService

            self._wave = AsyncWaveService()
        return self._wave

    @property
    def streamer(self):
        if self._streamer is None:
            from quantis.services.async_streamer import AsyncStreamer

            self._streamer = AsyncStreamer()
        return self._streamer

    @property
    def provider(self) -> PathProvider:
        return self._provider

    def shutdown(self) -> None:
        if self._finder is not None:
            self._finder.shutdown()
        if self._streamer is not None:
            self._streamer.shutdown()
        if self._downloader is not None:
            self._downloader.shutdown()
        from quantis.core.worker_pool import shutdown_worker_pool

        shutdown_worker_pool()
