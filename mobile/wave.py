"""«Моя волна» Яндекса: сессии /rotor/session, как в настольном Quantis.

Синхронная версия services/async_wave.py: новая сессия по сидам, догрузка
следующих треков, события feedback (начал, дослушал, пропустил) — по ним
Яндекс подстраивает волну. Вызывается из пула потоков.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import sources
from sources import Result

log = logging.getLogger(__name__)

_FROM = "web-wave_landing_screen-radio-wheel-default"
_QUEUE_SIZE = 5  # последние треки как контекст для догрузки (так делает веб)
_FINISH_SLACK = 5.0  # до конца меньше — дослушал, а не пропустил


@dataclass(frozen=True)
class Mood:
    name: str
    seeds: tuple[str, ...]
    color: str


MY_WAVE = Mood("Моя волна", ("user:onyourwave",), "#7C4DFF")

# Постоянные карточки (сиды проверены на API настольной версией).
MOODS: tuple[Mood, ...] = (
    Mood("Спокойно", ("mood:calm",), "#2EC4B6"),
    Mood("Энергия", ("mood:energetic",), "#FF8A00"),
    Mood("Радостно", ("mood:happy",), "#FFC93C"),
    Mood("Грусть", ("mood:sad",), "#3D5AFE"),
    Mood("Помечтать", ("mood:dream",), "#B388FF"),
    Mood("Работа", ("activity:work-background",), "#42A5F5"),
    Mood("Бег", ("activity:run",), "#76FF03"),
    Mood("Тренировка", ("activity:workout",), "#FF3D00"),
    Mood("В дорогу", ("activity:road-trip",), "#FF7043"),
    Mood("Вечеринка", ("activity:party",), "#D500F9"),
    Mood("Сон", ("activity:fall-asleep",), "#3949AB"),
    Mood("Любимое", ("diversity:favorite",), "#FF4081"),
    Mood("На русском", ("local-language:russian",), "#5C6BC0"),
)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class WaveSession:
    def __init__(self, token: str) -> None:
        self._client = sources._client(token)
        self.seeds: tuple[str, ...] = ()
        self._session: str | None = None
        self._batch: str | None = None
        self._albums: dict[str, int] = {}

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._client.base_url}{path}"
        return sources._yandex(lambda: self._client._request.post(url, json=body)) or {}

    def _tracks(self, sequence: Any) -> list[Result]:
        from yandex_music import Track

        results: list[Result] = []
        for item in sequence or []:
            raw = item.get("track") if isinstance(item, dict) else None
            if raw is None:
                continue
            try:
                track = Track.de_json(raw, self._client)
            except Exception:
                log.debug("Моя волна: пропуск трека", exc_info=True)
                continue
            result = sources.yandex_result(track)
            if result is None:
                continue
            if track.albums:
                self._albums[result.track_id] = int(track.albums[0].id)
            results.append(result)
        return results

    def _full_id(self, result: Result) -> str:
        """Сессии ждут «трек:альбом» — альбом известен из ответа."""
        album = self._albums.get(result.track_id)
        return f"{result.track_id}:{album}" if album else result.track_id

    def _new(self, seeds: tuple[str, ...], queue: list[str]) -> dict[str, Any]:
        body: dict[str, Any] = {
            "seeds": list(seeds),
            "includeTracksInResponse": True,
            "includeWaveModel": True,
            "interactive": True,
        }
        if queue:
            body["queue"] = queue
        return self._post("/rotor/session/new", body)

    def start(self, seeds: tuple[str, ...]) -> list[Result]:
        result = self._new(seeds, [])
        tracks = self._tracks(result.get("sequence"))
        if not tracks:
            raise RuntimeError(
                "Моя волна не вернула треков — попробуй другое настроение"
            )
        self.seeds = seeds
        self._session = result.get("radioSessionId")
        self._batch = result.get("batchId")
        self._feedback({"type": "radioStarted", "from": _FROM})
        return tracks

    def more(self, played: list[Result]) -> list[Result]:
        """Следующая порция треков; протухшая сессия открывается заново."""
        queue = [self._full_id(r) for r in played[-_QUEUE_SIZE:]]
        result: dict[str, Any] = {}
        if self._session:
            try:
                result = self._post(
                    f"/rotor/session/{self._session}/tracks", {"queue": queue}
                )
            except Exception:
                log.debug("Моя волна: догрузка по сессии", exc_info=True)
        if not result or result.get("unknownSession") or result.get("terminated"):
            result = self._new(self.seeds, queue)
            self._session = result.get("radioSessionId") or self._session
        if result.get("batchId"):
            self._batch = result["batchId"]
            self._feedback({"type": "radioStarted", "from": _FROM})
        return self._tracks(result.get("sequence"))

    def started(self, result: Result) -> None:
        self._feedback({"type": "trackStarted", "trackId": self._full_id(result)})

    def finished(self, result: Result, played_s: float, total_s: float) -> None:
        skipped = bool(total_s) and played_s < total_s - _FINISH_SLACK
        self._feedback(
            {
                "type": "skip" if skipped else "trackFinished",
                "trackId": self._full_id(result),
                "totalPlayedSeconds": round(played_s, 3),
            }
        )

    def _feedback(self, event: dict[str, Any]) -> None:
        if not self._session:
            return
        body: dict[str, Any] = {"event": {"timestamp": _now(), **event}, "from": _FROM}
        if self._batch and event.get("type") != "radioStarted":
            body["batchId"] = self._batch
        try:
            self._post(f"/rotor/session/{self._session}/feedback/", body)
        except Exception:
            log.debug("Моя волна: feedback %s", event.get("type"), exc_info=True)
