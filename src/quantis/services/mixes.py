"""Миксы на главной: подборки из собственной истории прослушиваний.

Сеть не нужна: «На повторе», по микс на любимых артистов и «Забытое» —
то, что раньше крутилось часто, а последние недели не звучало.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from quantis.models import Track
from quantis.models.playlist import Playlist
from quantis.utils.artists import primary_artist

MIX_TRACKS = 40
ARTIST_MIXES = 4
_MIN_TRACKS = 4
_MIN_ARTIST_TRACKS = 3
_FORGOTTEN_AFTER_SEC = 21 * 24 * 3600


class MixPlaylist(Playlist):
    """Микс: обычный плейлист плюс подпись и тип для карточки."""

    kind = "mix"

    def __init__(
        self,
        name: str,
        tracks: Iterable[Track],
        *,
        mix_id: str,
        subtitle: str,
    ) -> None:
        super().__init__(name, tracks, None)
        self.mix_id = mix_id
        self.subtitle = subtitle

    def get_tracks(self) -> tuple[Track, ...]:
        return tuple(self.tracks.values)


@dataclass(frozen=True, slots=True)
class MixSpec:
    """Микс до сборки Track: ключи записей истории в нужном порядке."""

    mix_id: str
    name: str
    subtitle: str
    keys: tuple[str, ...]


def plan_mixes(
    entries: Sequence[dict[str, Any]],
    liked_keys: Iterable[str] = (),
    *,
    now: float,
) -> list[MixSpec]:
    """Какие миксы собрать и из каких треков. Чистая функция — для тестов."""
    liked = set(liked_keys)
    listened = [e for e in entries if int(e.get("listen_count") or 0) > 0]
    by_listens = sorted(
        listened,
        key=lambda e: (-int(e.get("listen_count") or 0), -int(e["last_played_at"])),
    )
    specs: list[MixSpec] = []

    repeat = [e["track_key"] for e in by_listens if int(e["listen_count"]) >= 2]
    if len(repeat) >= _MIN_TRACKS:
        specs.append(
            MixSpec(
                "repeat",
                "На повторе",
                "Самое заслушанное",
                tuple(repeat[:MIX_TRACKS]),
            )
        )

    groups: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    for entry in entries:
        artist = primary_artist(str(entry.get("author") or ""))
        if not artist:
            continue
        key = artist.casefold()
        groups.setdefault(key, []).append(entry)
        names.setdefault(key, artist)

    def weight(group: list[dict[str, Any]]) -> int:
        listens = sum(int(e.get("listen_count") or 0) for e in group)
        return listens + sum(2 for e in group if e["track_key"] in liked)

    ranked = sorted(
        (k for k, g in groups.items() if len(g) >= _MIN_ARTIST_TRACKS),
        key=lambda k: (-weight(groups[k]), names[k].casefold()),
    )
    for key in ranked[:ARTIST_MIXES]:
        if weight(groups[key]) <= 0:
            continue
        group = sorted(
            groups[key],
            key=lambda e: (
                -int(e.get("listen_count") or 0),
                e["track_key"] not in liked,
                -int(e["last_played_at"]),
            ),
        )
        count = len(group)
        specs.append(
            MixSpec(
                f"artist:{key}",
                names[key],
                f"Микс · {_tracks_word(count)}",
                tuple(e["track_key"] for e in group[:MIX_TRACKS]),
            )
        )

    cutoff = now - _FORGOTTEN_AFTER_SEC
    forgotten = [
        e["track_key"]
        for e in by_listens
        if int(e["listen_count"]) >= 2 and int(e["last_played_at"]) < cutoff
    ]
    if len(forgotten) >= _MIN_TRACKS:
        specs.append(
            MixSpec(
                "forgotten",
                "Забытое",
                "Давно не звучало",
                tuple(forgotten[:MIX_TRACKS]),
            )
        )
    return specs


def build_mixes(
    specs: Sequence[MixSpec], tracks_by_key: dict[str, Track]
) -> list[MixPlaylist]:
    mixes: list[MixPlaylist] = []
    for spec in specs:
        tracks = [tracks_by_key[k] for k in spec.keys if k in tracks_by_key]
        if tracks:
            mixes.append(
                MixPlaylist(
                    spec.name, tracks, mix_id=spec.mix_id, subtitle=spec.subtitle
                )
            )
    return mixes


def _tracks_word(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return f"{count} трек"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return f"{count} трека"
    return f"{count} треков"
