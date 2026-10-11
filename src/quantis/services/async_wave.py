"""Моя волна — персональное радио Yandex на сессиях ``/rotor/session``.

Новый веб-клиент Яндекс Музыки (2026) запускает волну по сидам
(``mood:calm``, ``activity:run``, ``genre:rusrock`` …), а список доступных
«настроений» отдаёт колесо ``/wheel/new``. В ``yandex_music`` этих методов
нет, поэтому запросы идут через ``client._request`` (авторизация уже там).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from quantis.config.clients import Clients
from quantis.config.credentials import yandex_token
from quantis.models import Track, YandexTrack
from quantis.models.playlist import WavePlaylist
from quantis.services.yandex_finder import yandex_track_from_api

logger = logging.getLogger(__name__)

YANDEX_USER_WAVE_STATION = "user:onyourwave"
DEFAULT_WAVE_SEEDS: tuple[str, ...] = (YANDEX_USER_WAVE_STATION,)
_WAVE_FROM = "web-wave_landing_screen-radio-wheel-default"
_PLAY_FROM = "desktop_win-home-wave-default"
# Сколько последних треков отдаём серверу как контекст (так делает веб).
_QUEUE_SIZE = 5
# Если до конца трека осталось меньше — считаем, что дослушали, а не скипнули.
_FINISH_SLACK_SECONDS = 5.0


@dataclass(frozen=True)
class WaveMood:
    """Карточка колеса «Моей волны»: настроение, занятие, жанр, артист…"""

    id: str
    name: str
    seeds: tuple[str, ...]
    description: str = ""
    style: str = "DEFAULT"
    cover_uri: str | None = None
    color: str | None = None

    @property
    def is_control(self) -> bool:
        """«Встряхнуть» / «Назад к привычному» — управляющие карточки."""
        return self.style == "CONTROL_ACCENT"

    def cover_url(self, size: str = "200x200") -> str | None:
        if not self.cover_uri:
            return None
        uri = self.cover_uri.replace("%%", size)
        return uri if uri.startswith("http") else f"https://{uri}"

    @classmethod
    def from_wheel_item(cls, item: dict[str, Any]) -> WaveMood | None:
        if item.get("type") != "WAVE":
            return None
        data = item.get("data") or {}
        wave = data.get("wave") or {}
        seeds = tuple(wave.get("seeds") or ())
        if not seeds or not wave.get("name"):
            return None
        cover = (data.get("agent") or {}).get("cover") or {}
        return cls(
            id=str(item.get("id") or ",".join(seeds)),
            name=str(wave["name"]),
            seeds=seeds,
            description=str(wave.get("description") or ""),
            style=str(item.get("style") or "DEFAULT"),
            cover_uri=cover.get("uri"),
            color=cover.get("color"),
        )


def _catalog(
    kind: str, items: tuple[tuple[str, str, str], ...]
) -> tuple[WaveMood, ...]:
    return tuple(
        WaveMood(
            id=f"{kind}:{value}", name=name, seeds=(f"{kind}:{value}",), color=color
        )
        for value, name, color in items
    )


# Постоянные разделы страницы «Моя волна». Колесо Яндекса каждый раз отдаёт
# случайные 15–17 карточек, а эти сиды работают всегда (проверено на API).
WAVE_MOODS = _catalog(
    "mood",
    (
        ("calm", "Сохранять спокойствие", "#2EC4B6"),
        ("energetic", "Добавить энергии", "#FF8A00"),
        ("happy", "Радостно на душе", "#FFC93C"),
        ("sad", "Прожить эту грусть", "#3D5AFE"),
        ("dream", "Время помечтать", "#B388FF"),
        ("beautiful", "Здесь так красиво", "#F48FB1"),
        ("sentimental", "С теплом на сердце", "#E91E63"),
        ("autumn", "Туда, где осень", "#D35400"),
    ),
)
WAVE_ACTIVITIES = _catalog(
    "activity",
    (
        ("work-background", "В работу с головой", "#42A5F5"),
        ("run", "Бежать быстрее ветра", "#76FF03"),
        ("workout", "Тренироваться в ритме", "#FF3D00"),
        ("road-trip", "В дорогу", "#FF7043"),
        ("party", "Вечериниться", "#D500F9"),
        ("romantic-date", "Свидание на 10 из 10", "#C2185B"),
        ("fall-asleep", "Сон зовёт", "#3949AB"),
    ),
)
WAVE_GENRES = _catalog(
    "genre",
    (
        ("allrock", "Е-е-е, рок!", "#E53935"),
        ("pop", "Это поп!", "#FF4FA3"),
        ("rap", "Рэп и хип-хоп", "#C9A227"),
        ("electronics", "Электроника", "#00B8D4"),
        ("dance", "Танцевальная", "#E040FB"),
        ("indie", "Инди", "#9CCC65"),
        ("rnb", "R&B и соул", "#8E24AA"),
        ("jazz", "Джаз", "#FFB300"),
        ("metal", "Метал", "#B71C1C"),
        ("punk", "Устроить панк", "#FF1744"),
        ("folk", "Фолк", "#8D6E63"),
        ("soundtrack", "Саундтреки", "#5C6BC0"),
        ("classicalmusic", "Классическая музыка", "#D4AF37"),
        ("bard", "Авторская песня", "#A1887F"),
        ("estrada", "Блистать под эстраду", "#F06292"),
        ("soviet", "Старое доброе советское", "#D32F2F"),
    ),
)
WAVE_CHARACTER = (
    WaveMood(
        id="diversity:favorite",
        name="Любимое",
        seeds=("diversity:favorite",),
        description="Моя волна по характеру",
        color="#FF4081",
    ),
    WaveMood(
        id="local-language:russian",
        name="Только на русском",
        seeds=("local-language:russian",),
        description="Моя волна по языку",
        color="#5C6BC0",
    ),
    WaveMood(
        id="local-language:english",
        name="Только на английском",
        seeds=("local-language:english",),
        description="Моя волна по языку",
        color="#26A69A",
    ),
)
DEFAULT_WAVE_MOOD = WaveMood(
    id=YANDEX_USER_WAVE_STATION,
    name="Моя волна",
    seeds=DEFAULT_WAVE_SEEDS,
    description="Персональный поток под ваш вкус",
    color="#7C4DFF",
)


class AsyncWaveService:
    """Сессия «Моя волна»: старт по сидам, feedback, догрузка батчей."""

    def __init__(self) -> None:
        self._seeds: tuple[str, ...] = DEFAULT_WAVE_SEEDS
        self._session_id: str | None = None
        self._batch_id: str | None = None
        self._play_id: str | None = None
        self._album_ids: dict[str, int] = {}
        self._durations_ms: dict[str, int] = {}
        self._feedback_tail: asyncio.Task | None = None

    @property
    def seeds(self) -> tuple[str, ...]:
        return self._seeds

    async def start_yandex_wave(
        self, seeds: Sequence[str] | None = None, *, name: str | None = None
    ) -> WavePlaylist | None:
        """Новая сессия волны. Без ``seeds`` — обычная «Моя волна»."""
        client = self._client()
        if client is None:
            return None

        wanted = tuple(seeds) if seeds else DEFAULT_WAVE_SEEDS
        result = await self._new_session(client, wanted, queue=())
        if result is None:
            return None
        tracks = self._tracks_from_sequence(client, result.get("sequence"))
        if not tracks:
            logger.warning("Моя волна: пустая последовательность треков")
            return None

        self._seeds = wanted
        self._session_id = result.get("radioSessionId")
        self._batch_id = result.get("batchId")
        await self._send_feedback(client, {"type": "radioStarted", "from": _WAVE_FROM})

        wave = result.get("wave") or {}
        playlist = WavePlaylist(
            name=name or wave.get("name") or "Моя волна",
            tracks=tracks,
            source="yandex",
            seeds=wanted,
            session_id=self._session_id,
            batch_id=self._batch_id,
        )
        playlist.set_current_track(0)
        return playlist

    async def fetch_wheel(self, seeds: Sequence[str] | None = None) -> list[WaveMood]:
        """Карточки колеса для текущей волны. Список персональный и меняется
        после каждого переключения — перезапрашивать после ``start_yandex_wave``.
        """
        client = self._client()
        if client is None:
            return []
        body = {
            "context": {"type": "WAVE", "data": {"seeds": list(seeds or self._seeds)}},
            "feedbacks": [],
        }
        try:
            result = await client._request.post(
                f"{client.base_url}/wheel/new", json=body
            )
        except Exception:
            logger.exception("Моя волна: не удалось получить колесо настроений")
            return []
        items = (result or {}).get("items") or []
        moods = [WaveMood.from_wheel_item(item) for item in items]
        return [mood for mood in moods if mood is not None]

    async def notify_track_started(
        self, track: Track, playlist: WavePlaylist | None = None
    ) -> None:
        client = self._client(quiet=True)
        if client is None:
            return
        self._adopt(playlist)
        self._play_id = self._generate_play_id()
        await self._send_play_start_track(client, track)
        await self._send_feedback(
            client,
            {"type": "trackStarted", "trackId": self._full_track_id(track)},
        )

    async def continue_after_finish(
        self,
        playlist: WavePlaylist,
        finished: Track,
        *,
        played_seconds: float,
    ) -> Track | None:
        """Feedback о конце (или скипе) трека + следующий трек.

        Когда батч кончился — подгружает новый с последними треками в ``queue``.
        """
        client = self._client(quiet=True)
        if client is None:
            # Без API — просто следующий в уже загруженном списке
            return self._linear_next(playlist)

        self._adopt(playlist)
        total = self._duration_seconds(finished)
        skipped = bool(total) and played_seconds < total - _FINISH_SLACK_SECONDS
        event = {
            "type": "skip" if skipped else "trackFinished",
            "trackId": self._full_track_id(finished),
            "totalPlayedSeconds": round(played_seconds, 3),
        }

        async def finish_feedback() -> None:
            await self._send_play_end_track(client, finished, played_seconds)
            await self._send_feedback(client, event)

        idx = playlist.tracks._index
        if idx + 1 >= len(playlist):
            # Новый батч сервер подбирает по фидбеку — тут отчёт нужен до запроса.
            self._in_background(finish_feedback)
            await self.drain()
            more = await self._fetch_more(client, playlist)
            added = playlist.append_tracks(more)
            logger.info("Моя волна: подгружено ещё %s треков", added)
        else:
            # Отчёты Яндексу плееру не нужны: четыре запроса подряд (~0,4 с)
            # раньше стояли между «следующий» и запросом ссылки на трек.
            self._in_background(finish_feedback)

        nxt = self._linear_next(playlist)
        if nxt is not None:
            self._in_background(lambda: self.notify_track_started(nxt, playlist))
        return nxt

    def _in_background(self, make_coro) -> None:
        """Фоновые отчёты по очереди: «закончен» всегда уходит раньше «начат»."""
        previous = self._feedback_tail

        async def run() -> None:
            if previous is not None:
                with contextlib.suppress(Exception):
                    await previous
            try:
                await make_coro()
            except Exception:
                logger.debug("Моя волна: фоновый отчёт", exc_info=True)

        self._feedback_tail = asyncio.ensure_future(run())

    async def drain(self) -> None:
        """Дождаться фоновых отчётов (перед подгрузкой батча и в тестах)."""
        while self._feedback_tail is not None and not self._feedback_tail.done():
            await self._feedback_tail

    # --- сессия -------------------------------------------------------------

    def _client(self, *, quiet: bool = False):
        if not yandex_token():
            if not quiet:
                logger.info("Моя волна: нет токена Yandex")
            return None
        client = Clients().get_yandex_client()
        if client is None and not quiet:
            logger.warning("Моя волна: клиент Yandex недоступен")
        return client

    def _adopt(self, playlist: WavePlaylist | None) -> None:
        """Плейлист мог быть склонирован UI — берём сессию из него."""
        if playlist is None:
            return
        if playlist.session_id:
            self._session_id = playlist.session_id
            self._seeds = playlist.seeds
        if playlist.batch_id:
            self._batch_id = playlist.batch_id

    async def _new_session(
        self, client, seeds: tuple[str, ...], queue: Sequence[str]
    ) -> dict[str, Any] | None:
        body: dict[str, Any] = {
            "seeds": list(seeds),
            "includeTracksInResponse": True,
            "includeWaveModel": True,
            "interactive": True,
        }
        if queue:
            body["queue"] = list(queue)
        try:
            return await client._request.post(
                f"{client.base_url}/rotor/session/new", json=body
            )
        except Exception:
            logger.exception("Моя волна: не удалось открыть сессию %s", seeds)
            return None

    async def _fetch_more(self, client, playlist: WavePlaylist) -> list[YandexTrack]:
        queue = [self._full_track_id(t) for t in playlist.get_tracks()[-_QUEUE_SIZE:]]
        result = None
        if self._session_id:
            try:
                result = await client._request.post(
                    f"{client.base_url}/rotor/session/{self._session_id}/tracks",
                    json={"queue": queue},
                )
            except Exception:
                logger.debug("Моя волна: tracks по сессии", exc_info=True)
        if not result or result.get("unknownSession") or result.get("terminated"):
            # Сессия протухла — открываем новую с тем же контекстом.
            result = await self._new_session(client, playlist.seeds, queue)
            if result is None:
                return []
            new_session = result.get("radioSessionId")
            if new_session:
                self._session_id = new_session
                playlist.session_id = new_session

        new_batch = result.get("batchId")
        if new_batch:
            self._batch_id = new_batch
            playlist.batch_id = new_batch
            await self._send_feedback(
                client, {"type": "radioStarted", "from": _WAVE_FROM}
            )
        return self._tracks_from_sequence(client, result.get("sequence"))

    async def _send_feedback(self, client, event: dict[str, Any]) -> None:
        if not self._session_id:
            return
        body: dict[str, Any] = {
            "event": {"timestamp": self._timestamp(), **event},
            "from": _WAVE_FROM,
        }
        if self._batch_id and event.get("type") != "radioStarted":
            body["batchId"] = self._batch_id
        try:
            await client._request.post(
                f"{client.base_url}/rotor/session/{self._session_id}/feedback/",
                json=body,
            )
        except Exception:
            logger.debug("Моя волна: feedback %s", event.get("type"), exc_info=True)

    # --- plays (история прослушиваний) ---------------------------------------

    def _duration_seconds(self, track: Track) -> float:
        ms = self._durations_ms.get(str(track.track_id))
        if not ms:
            ms = int(getattr(track, "duration_ms", 0) or 0)
        if ms and ms > 0:
            return float(ms) / 1000.0
        return 0.0

    async def _send_play_start_track(self, client, track: Track) -> None:
        album_id = await self._album_id_for(client, track)
        total_seconds = self._duration_seconds(track)
        try:
            # Как в MarshalX Radio.__send_play_start_track
            await client.play_audio(
                from_=_PLAY_FROM,
                track_id=track.track_id,
                album_id=album_id,
                play_id=self._play_id,
                track_length_seconds=0,
                total_played_seconds=0,
                end_position_seconds=total_seconds,
            )
        except Exception:
            logger.debug("Моя волна: play_audio start", exc_info=True)

    async def _send_play_end_track(
        self, client, track: Track, played_seconds: float
    ) -> None:
        album_id = await self._album_id_for(client, track)
        total_seconds = self._duration_seconds(track) or max(played_seconds, 1.0)
        try:
            # Как в MarshalX Radio.__send_play_end_track
            await client.play_audio(
                from_=_PLAY_FROM,
                track_id=track.track_id,
                album_id=album_id,
                play_id=self._play_id,
                track_length_seconds=int(total_seconds),
                total_played_seconds=played_seconds,
                end_position_seconds=total_seconds,
            )
        except Exception:
            logger.debug("Моя волна: play_audio end", exc_info=True)

    async def _album_id_for(self, client, track: Track) -> int:
        key = str(track.track_id)
        if key in self._album_ids:
            return self._album_ids[key]
        try:
            infos = await client.tracks(int(track.track_id))
            if infos:
                info = infos[0]
                dur = getattr(info, "duration_ms", None)
                if dur:
                    self._durations_ms[key] = int(dur)
                albums = getattr(info, "albums", None) or []
                if albums:
                    album_id = int(albums[0].id)
                    self._album_ids[key] = album_id
                    return album_id
        except Exception:
            logger.debug("Моя волна: album_id", exc_info=True)
        return 0

    # --- утилиты --------------------------------------------------------------

    def _full_track_id(self, track: Track) -> str:
        """Сессии ждут ``track:album`` — альбом знаем из sequence."""
        key = str(track.track_id)
        album_id = self._album_ids.get(key)
        return f"{key}:{album_id}" if album_id else key

    @staticmethod
    def _linear_next(playlist: WavePlaylist) -> Track | None:
        idx = playlist.tracks._index
        if idx + 1 >= len(playlist):
            return None
        playlist.set_current_track(idx + 1)
        return playlist.get_current_track()

    @staticmethod
    def _generate_play_id() -> str:
        return f"{int(random.random() * 1000)}-{int(random.random() * 1000)}-{int(random.random() * 1000)}"

    @staticmethod
    def _timestamp() -> str:
        now = datetime.now(timezone.utc)
        return now.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def _tracks_from_sequence(self, client, sequence: Any) -> list[YandexTrack]:
        if not sequence:
            return []
        from yandex_music import Track as ApiTrack

        tracks: list[YandexTrack] = []
        for item in sequence:
            raw = item.get("track") if isinstance(item, dict) else None
            if raw is None:
                continue
            try:
                track = ApiTrack.de_json(raw, client)
                if track is None:
                    continue
                yt = yandex_track_from_api(track)
                tracks.append(yt)
                key = str(yt.track_id)
                albums = getattr(track, "albums", None) or []
                if albums:
                    self._album_ids[key] = int(albums[0].id)
                dur = getattr(track, "duration_ms", None)
                if dur:
                    self._durations_ms[key] = int(dur)
            except Exception:
                logger.debug("Моя волна: пропуск трека в sequence", exc_info=True)
        return tracks
