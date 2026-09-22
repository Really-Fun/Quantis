"""Кэширование stream URL с TTL и LRU."""

from __future__ import annotations

import functools
from collections import OrderedDict
from time import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from quantis.models import Track


def cached_stream_url(func: Callable) -> Callable:
    """Декоратор для кэширования прямых URL треков внутри методов класса Streamer."""

    @functools.wraps(func)
    async def wrapper(self, track: "Track", *args, **kwargs) -> str | None:
        track_key = f"{track.source}:{track.track_id}"
        now = time()
        ttl = getattr(self, "_URL_CACHE_TTL_SEC", 30 * 60)
        max_size = getattr(self, "_URL_CACHE_MAX", 64)

        if not isinstance(self._cache, OrderedDict):
            self._cache = OrderedDict(self._cache)

        cached = self._cache.get(track_key)
        if cached is not None and (now - cached[1] < ttl):
            self._cache.move_to_end(track_key)
            return cached[0]

        expired = [k for k, (_, ts) in self._cache.items() if now - ts >= ttl]
        for key in expired:
            self._cache.pop(key, None)

        url = await func(self, track, *args, **kwargs)

        if url is not None:
            self._cache[track_key] = (url, now)
            self._cache.move_to_end(track_key)
            while len(self._cache) > max_size:
                self._cache.popitem(last=False)

        return url

    return wrapper
