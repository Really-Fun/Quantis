"""Короткий факт об исполнителе из Wikipedia REST."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote

import aiohttp

from quantis.version import get_version

from script import first_sentence

logger = logging.getLogger(__name__)

_WIKI_SUMMARY = "https://ru.wikipedia.org/api/rest_v1/page/summary/{title}"
_TIMEOUT = aiohttp.ClientTimeout(total=1.5)


def _user_agent() -> str:
    return (
        f"Quantis/{get_version()} "
        "(https://github.com/Really-Fun/Quantis; nfs-speaker plugin)"
    )


def fact_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    if str(payload.get("type") or "") == "disambiguation":
        return None
    extract = first_sentence(str(payload.get("extract") or ""))
    return extract or None


class WikipediaFacts:
    """Кэш фактов по исполнителю на время сессии."""

    def __init__(self) -> None:
        self._cache: dict[str, str | None] = {}

    async def fact_for(self, author: str) -> str | None:
        key = " ".join(str(author or "").split()).lower()
        if not key:
            return None
        if key in self._cache:
            return self._cache[key]
        fact = await self._fetch(author)
        self._cache[key] = fact
        return fact

    async def _fetch(self, author: str) -> str | None:
        url = _WIKI_SUMMARY.format(title=quote(author.strip(), safe=""))
        headers = {
            "User-Agent": _user_agent(),
            "Accept": "application/json",
        }
        try:
            async with aiohttp.ClientSession(
                timeout=_TIMEOUT, headers=headers
            ) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        return None
                    payload = await response.json(content_type=None)
        except Exception:
            logger.debug("Wikipedia: нет саммари для %s", author, exc_info=True)
            return None
        return fact_from_payload(payload)
