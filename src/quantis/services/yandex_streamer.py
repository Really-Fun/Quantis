"""Yandex Music streaming."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from asyncio import get_running_loop
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from quantis.models import Track

logger = logging.getLogger(__name__)


class AsyncStreamerInterface(ABC):
    @abstractmethod
    async def get_stream_url(self, track: Track) -> str | None: ...


class AsyncYandexStreamer(AsyncStreamerInterface):
    def __init__(self, executor: ThreadPoolExecutor) -> None:
        self._executor = executor

    async def get_stream_url(self, track: Track) -> str | None:
        return await get_running_loop().run_in_executor(
            self._executor, self._sync_get_stream_url, track
        )

    def _yandex_token(self) -> str | None:
        from keyring import get_password

        from quantis.config.constants import SERVICE_NAME_YANDEX, USER

        return get_password(SERVICE_NAME_YANDEX, USER)

    @staticmethod
    def pick_best_download_info(infos: list[Any]) -> Any | None:
        """Полный трек (не preview), предпочтительно mp3 с макс. bitrate."""
        if not infos:
            return None
        full = [item for item in infos if not bool(getattr(item, "preview", False))]
        candidates = full or list(infos)

        def score(item: Any) -> tuple[int, int, int]:
            preview = 1 if bool(getattr(item, "preview", False)) else 0
            codec = str(getattr(item, "codec", "") or "").lower()
            codec_rank = 2 if codec == "mp3" else (1 if codec in ("aac", "mp4") else 0)
            bitrate = int(getattr(item, "bitrate_in_kbps", 0) or 0)
            return (-preview, codec_rank, bitrate)

        return max(candidates, key=score)

    def _sync_get_stream_url(self, track: Track) -> str | None:
        token = self._yandex_token()
        if not token:
            return None
        try:
            from yandex_music import Client

            track_id = int(track.track_id)
            client = Client(token)
            track_info = client.tracks(track_id)
            if not track_info:
                return None
            download_info = track_info[0].get_download_info()
            chosen = self.pick_best_download_info(list(download_info or []))
            if chosen is None:
                return None
            if bool(getattr(chosen, "preview", False)):
                logger.warning(
                    "Yandex отдал только preview (~30с) для «%s» — "
                    "нужен Plus / валидный токен. codec=%s bitrate=%s",
                    track.title,
                    getattr(chosen, "codec", "?"),
                    getattr(chosen, "bitrate_in_kbps", "?"),
                )
            else:
                logger.debug(
                    "Yandex stream «%s»: codec=%s bitrate=%s",
                    track.title,
                    getattr(chosen, "codec", "?"),
                    getattr(chosen, "bitrate_in_kbps", "?"),
                )
            return chosen.get_direct_link()
        except Exception:
            logger.exception("Не удалось получить URL потока Яндекс.Музыки: %s", track)
            return None
