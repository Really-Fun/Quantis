"""Имя артиста для группировки: «A, B feat. C» — это A."""

from __future__ import annotations

import re

# Только явные разделители соавторов. «&», «и», «x» не трогаем: это часть
# названий групп («Король и Шут», «Simon & Garfunkel», «Lil Nas X»).
_SPLIT_ARTISTS = re.compile(
    r"\s*(?:,|;|/|\bfeat\.|\bfeat\b|\bft\.|\bft\b|\bfeaturing\b)\s*",
    re.IGNORECASE,
)


def primary_artist(author: str) -> str:
    """Первый артист из «A, B feat. C» — по нему группируются миксы и топ."""
    head = _SPLIT_ARTISTS.split(author.strip(), maxsplit=1)[0]
    return head.strip() or author.strip()
