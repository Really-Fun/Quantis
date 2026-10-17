"""Какая «Моя волна» играет: Яндекс (если есть токен) или YouTube Music."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Sequence

from quantis.config.credentials import yandex_token
from quantis.models import Track
from quantis.models.playlist import WavePlaylist

if TYPE_CHECKING:
    from quantis.services.async_wave import AsyncWaveService, WaveMood
    from quantis.services.youtube_wave import YoutubeWaveService

logger = logging.getLogger(__name__)


class WaveRouter:
    """Новую волну открывает Яндекс, а без токена (или если он не ответил) —
    YouTube. Начатая волна продолжается тем сервисом, что её открыл
    (``WavePlaylist.source``), даже если токен за это время поменялся.
    """

    def __init__(
        self,
        make_yandex: Callable[[], AsyncWaveService],
        make_youtube: Callable[[], YoutubeWaveService],
    ) -> None:
        self._make_yandex = make_yandex
        self._make_youtube = make_youtube
        self._yandex: AsyncWaveService | None = None
        self._youtube: YoutubeWaveService | None = None

    @property
    def yandex(self) -> AsyncWaveService:
        if self._yandex is None:
            self._yandex = self._make_yandex()
        return self._yandex

    @property
    def youtube(self) -> YoutubeWaveService:
        if self._youtube is None:
            self._youtube = self._make_youtube()
        return self._youtube

    @staticmethod
    def uses_yandex() -> bool:
        return bool(yandex_token())

    def _for(
        self, playlist: WavePlaylist | None
    ) -> AsyncWaveService | YoutubeWaveService:
        if playlist is not None and playlist.source == "youtube":
            return self.youtube
        if playlist is None and not self.uses_yandex():
            return self.youtube
        return self.yandex

    async def start_wave(
        self,
        seeds: Sequence[str] | None = None,
        *,
        name: str | None = None,
        taste: Sequence[Track] = (),
    ) -> WavePlaylist | None:
        if self.uses_yandex():
            playlist = await self.yandex.start_yandex_wave(seeds, name=name)
            if playlist is not None:
                return playlist
            logger.info("Моя волна: Яндекс не ответил — включаем YouTube")
        return await self.youtube.start_wave(seeds, name=name, taste=taste)

    async def fetch_wheel(self, seeds: Sequence[str] | None = None) -> list[WaveMood]:
        if self.uses_yandex():
            return await self.yandex.fetch_wheel(seeds)
        return await self.youtube.fetch_wheel(seeds)

    async def notify_track_started(
        self, track: Track, playlist: WavePlaylist | None = None
    ) -> None:
        await self._for(playlist).notify_track_started(track, playlist)

    async def continue_after_finish(
        self,
        playlist: WavePlaylist,
        finished: Track,
        *,
        played_seconds: float,
    ) -> Track | None:
        return await self._for(playlist).continue_after_finish(
            playlist, finished, played_seconds=played_seconds
        )

    async def drain(self) -> None:
        if self._yandex is not None:
            await self._yandex.drain()
