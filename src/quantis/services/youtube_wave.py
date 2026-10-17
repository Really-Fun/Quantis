"""«Моя волна» без Яндекса — радио YouTube Music по тем же сидам.

Сиды остаются яндексовскими (``mood:calm``, ``activity:run``, ``genre:jazz``…),
чтобы карта настроений и карточки страницы работали без изменений. Сид
превращается в поисковый запрос, запрос — в плейлист YouTube Music, а
плейлист — в бесконечное радио (``get_watch_playlist(radio=True)``).

У YouTube нет фидбека как у ``/rotor/session``, поэтому вкус ведём сами:
дослушанный трек становится сидом следующей пачки, а артиста, которого
скипнули дважды, волна больше не ставит.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections import Counter
from typing import Any, AsyncIterator, Callable, Sequence

from quantis.config import Clients
from quantis.models import Track, YoutubeTrack
from quantis.models.playlist import WavePlaylist
from quantis.services.async_recommendation import youtube_tracks_from_watch
from quantis.services.async_wave import (
    DEFAULT_WAVE_SEEDS,
    WaveMood,
    is_skip,
)
from quantis.services.url_resolver import is_youtube_video_id

logger = logging.getLogger(__name__)

# Запросы подобраны по живому поиску YouTube Music (язык ru, 2026-10): по
# каждому первой в выдаче идёт подходящая официальная подборка. Прямые
# «грустные песни» или «музыка для вечеринки» находят иракские и
# панджабские подборки, поэтому часть запросов — на английском.
SEED_QUERIES: dict[str, str] = {
    "mood:calm": "спокойная поп музыка",
    "mood:energetic": "энергичная музыка",
    "mood:happy": "хорошее настроение",
    "mood:sad": "sad pop",
    "mood:dream": "dream pop",
    "mood:beautiful": "красивая музыка",
    "mood:sentimental": "баллады",
    "mood:autumn": "autumn vibes",
    "activity:work-background": "музыка для работы",
    "activity:run": "музыка для бега",
    "activity:workout": "музыка для тренировки",
    "activity:road-trip": "road trip",
    "activity:party": "party hits",
    "activity:romantic-date": "песни о любви",
    "activity:fall-asleep": "сон",
    "genre:allrock": "рок хиты",
    "genre:pop": "поп хиты",
    "genre:rap": "хип-хоп хиты",
    "genre:electronics": "электронная музыка",
    "genre:dance": "танцевальная музыка",
    "genre:indie": "инди хиты",
    "genre:rnb": "соул",
    "genre:jazz": "джаз",
    "genre:metal": "метал",
    "genre:punk": "панк",
    "genre:folk": "фолк музыка",
    "genre:soundtrack": "саундтреки из фильмов",
    "genre:classicalmusic": "классическая музыка",
    "genre:bard": "бардовские песни",
    "genre:estrada": "российская эстрада",
    "genre:soviet": "советские песни",
    "local-language:russian": "русские хиты",
    "local-language:english": "pop hits",
}
# Официальных подборок под эти сиды у YouTube Music нет, а на запрос он
# подсовывает чужие (украинский поп, «Дискотека 2026») — только плейлисты
# пользователей.
_COMMUNITY_SEEDS = frozenset(
    {"genre:bard", "genre:estrada", "genre:soviet", "local-language:russian"}
)
# Волны «по вкусу»: сид — трек из истории, а не запрос.
_TASTE_PREFIXES = ("user:", "diversity:")
_FALLBACK_QUERY = "популярная музыка"

BATCH_SIZE = 10
_WATCH_FETCH_LIMIT = 25
# Часовые сборники и стримы в волне не нужны.
_MAX_TRACK_MS = 12 * 60 * 1000
# Сколько раз скипнуть артиста, чтобы волна перестала его ставить.
_ARTIST_SKIP_LIMIT = 2
# Из скольких плейлистов пользователей выбираем — чтобы одно и то же
# настроение не начиналось всегда одинаково. Официальную берём первую:
# ниже в выдаче они уже не по теме.
_PLAYLIST_PICK = 3
# Сколько якорей пробуем, если радио от них пустое.
_ANCHOR_TRIES = 4
# Из скольких недавних треков истории выбираем сид «по вкусу».
_TASTE_PICK = 8
# Подборки самого YouTube Music; пользовательские плейлисты — это часто
# часовые миксы и перезаливы «16D AUDIO».
_OFFICIAL_PLAYLIST_PREFIX = "RDCLAK"
_UGC_VIDEO = "MUSIC_VIDEO_TYPE_UGC"
# Пользовательские видео выкидываем, только если без них хватает треков:
# советская эстрада и барды почти целиком UGC.
_MIN_NON_UGC = 3


def seed_query(seeds: Sequence[str]) -> str:
    """«спокойная музыка» + «музыка для работы» → «спокойная музыка для работы»."""
    words: list[str] = []
    for seed in seeds:
        query = SEED_QUERIES.get(seed)
        if query is None:
            query = seed.partition(":")[2].replace("-", " ")
        words.extend(query.split())
    return " ".join(dict.fromkeys(words)) or _FALLBACK_QUERY


def is_taste_wave(seeds: Sequence[str]) -> bool:
    return all(seed.startswith(_TASTE_PREFIXES) for seed in seeds)


class YoutubeWaveService:
    """Волна на YouTube Music: старт по сидам, догрузка по дослушанным трекам.

    ``WavePlaylist.session_id`` хранит якорь волны — ``pl:<playlistId>`` или
    ``v:<videoId>``: от него берётся радио, когда своих сидов ещё нет.
    """

    def __init__(self, youtube_finder: Any, client: Any | None = None) -> None:
        self._finder = youtube_finder
        self._client = client
        self._artist_skips: Counter[str] = Counter()
        self._played: set[str] = set()
        # Дослушанные треки — сиды следующих пачек (последний — первым).
        self._liked: list[str] = []

    @property
    def _yt(self) -> Any:
        if self._client is None:
            self._client = Clients().get_youtube_client()
        return self._client

    async def start_wave(
        self,
        seeds: Sequence[str] | None = None,
        *,
        name: str | None = None,
        taste: Sequence[Track] = (),
    ) -> WavePlaylist | None:
        wanted = tuple(seeds) if seeds else DEFAULT_WAVE_SEEDS
        anchor: str | None = None
        tracks: list[Track] = []
        tries = 0
        async for anchor in self._anchors(wanted, taste):
            tracks = await self._radio(anchor, exclude_ids=set())
            tries += 1
            if tracks or tries >= _ANCHOR_TRIES:
                break
            logger.info("Моя волна (YouTube): пустое радио для %s", anchor)
        if not tracks or anchor is None:
            logger.warning("Моя волна (YouTube): не нашли, с чего начать %s", wanted)
            return None

        self._artist_skips.clear()
        self._played.clear()
        self._liked.clear()
        playlist = WavePlaylist(
            name=name or "Моя волна",
            tracks=tracks,
            source="youtube",
            seeds=wanted,
            session_id=anchor,
        )
        playlist.set_current_track(0)
        return playlist

    async def fetch_wheel(self, seeds: Sequence[str] | None = None) -> list[WaveMood]:
        """Персонального колеса у YouTube нет — страница покажет только каталог."""
        return []

    async def notify_track_started(
        self, track: Track, playlist: WavePlaylist | None = None
    ) -> None:
        self._played.add(str(track.track_id))

    async def continue_after_finish(
        self,
        playlist: WavePlaylist,
        finished: Track,
        *,
        played_seconds: float,
    ) -> Track | None:
        total = int(getattr(finished, "duration_ms", 0) or 0) / 1000.0
        if is_skip(total, played_seconds):
            self._artist_skips[_artist_key(finished)] += 1
        elif is_youtube_video_id(str(finished.track_id)):
            self._liked.append(str(finished.track_id))

        nxt = self._next_allowed(playlist)
        if nxt is not None:
            return nxt
        added = await self._extend(playlist)
        logger.info("Моя волна (YouTube): подгружено ещё %s треков", added)
        return self._next_allowed(playlist)

    async def drain(self) -> None:
        """Фоновых отчётов нет — для симметрии с ``AsyncWaveService``."""

    # --- подбор ---------------------------------------------------------------

    async def _anchors(
        self, seeds: tuple[str, ...], taste: Sequence[Track]
    ) -> AsyncIterator[str]:
        """Якоря по убыванию качества; лениво — поиск только если прошлый
        якорь дал пустое радио (так бывает у плейлистов пользователей)."""
        if is_taste_wave(seeds):
            pool = list(taste[:_TASTE_PICK])
            random.shuffle(pool)
            for track in pool:
                video_id = await self._video_id_for(track)
                if video_id:
                    yield f"v:{video_id}"
            # Истории ещё нет — начинаем с популярного.
            queries = [_FALLBACK_QUERY]
        else:
            # Смесь «грусть + дорога» ищем по сидам по отдельности: на
            # склеенный запрос YouTube находит что попало (филиппинский поп).
            queries = [seed_query((seed,)) for seed in seeds]
        official_ok = not any(seed in _COMMUNITY_SEEDS for seed in seeds)
        fallbacks: list[str] = []
        for query in dict.fromkeys(queries):
            official, others = await self._search_anchors(query)
            if official and official_ok:
                yield f"pl:{official[0]}"
            fallbacks.extend(others)
        for anchor in dict.fromkeys(fallbacks):
            yield anchor

    async def _search_anchors(self, query: str) -> tuple[list[str], list[str]]:
        """Официальные плейлисты из выдачи и запасные якоря: несколько
        плейлистов пользователей вперемешку, затем первый трек."""
        results = await self._call(lambda: self._yt.search(query, limit=20))
        official: list[str] = []
        playlists: list[str] = []
        first_song: str | None = None
        for item in results or []:
            kind = item.get("resultType")
            browse_id = str(item.get("browseId") or "")
            if kind == "playlist" and browse_id.startswith("VL"):
                playlist_id = browse_id.removeprefix("VL")
                if playlist_id.startswith(_OFFICIAL_PLAYLIST_PREFIX):
                    official.append(playlist_id)
                else:
                    playlists.append(playlist_id)
            elif kind in ("song", "video") and first_song is None:
                video_id = str(item.get("videoId") or "")
                if is_youtube_video_id(video_id):
                    first_song = video_id
        picks = playlists[:_PLAYLIST_PICK]
        random.shuffle(picks)
        others = [f"pl:{playlist_id}" for playlist_id in picks]
        if first_song:
            others.append(f"v:{first_song}")
        return official, others

    async def _video_id_for(self, track: Track) -> str | None:
        if isinstance(track, YoutubeTrack) and is_youtube_video_id(str(track.track_id)):
            return str(track.track_id)
        query = f"{track.title} {track.author}".strip()
        results = await self._call(lambda: self._yt.search(query, limit=10))
        for item in results or []:
            video_id = str(item.get("videoId") or "")
            if item.get("resultType") in ("song", "video") and is_youtube_video_id(
                video_id
            ):
                return video_id
        return None

    async def _radio(self, anchor: str, *, exclude_ids: set[str]) -> list[Track]:
        kind, _, value = anchor.partition(":")
        if kind == "pl":
            call = lambda: self._yt.get_watch_playlist(  # noqa: E731
                playlistId=value, radio=True, limit=_WATCH_FETCH_LIMIT
            )
        else:
            call = lambda: self._yt.get_watch_playlist(  # noqa: E731
                videoId=value, limit=_WATCH_FETCH_LIMIT
            )
        result = _prefer_non_ugc(await self._call(call))
        tracks = youtube_tracks_from_watch(
            result, limit=_WATCH_FETCH_LIMIT, exclude_ids=set(exclude_ids)
        )
        tracks = [t for t in tracks if self._wanted(t)]
        return tracks[:BATCH_SIZE]

    async def _extend(self, playlist: WavePlaylist) -> int:
        existing = {str(t.track_id) for t in playlist.tracks.values} | self._played
        anchors = [f"v:{vid}" for vid in reversed(self._liked[-3:])]
        if playlist.session_id:
            anchors.append(playlist.session_id)
        for anchor in anchors:
            more = await self._radio(anchor, exclude_ids=existing)
            if more:
                return playlist.append_tracks(more)
        return 0

    def _wanted(self, track: Track) -> bool:
        duration = int(getattr(track, "duration_ms", 0) or 0)
        if duration > _MAX_TRACK_MS:
            return False
        return self._artist_skips[_artist_key(track)] < _ARTIST_SKIP_LIMIT

    def _next_allowed(self, playlist: WavePlaylist) -> Track | None:
        """Следующий трек очереди, минуя артистов, которых скипают."""
        tracks = playlist.tracks.values
        idx = playlist.tracks._index + 1
        while idx < len(tracks):
            if self._wanted(tracks[idx]):
                playlist.set_current_track(idx)
                return playlist.get_current_track()
            idx += 1
        # Пропущенные хвосты не должны снова всплыть при догрузке.
        if len(tracks):
            playlist.set_current_track(len(tracks) - 1)
        return None

    async def _call(self, fn: Callable[[], Any]) -> Any:
        try:
            return await asyncio.get_running_loop().run_in_executor(
                self._finder.executor, fn
            )
        except Exception:
            logger.exception("Моя волна (YouTube): запрос к YouTube Music")
            return None


def _prefer_non_ugc(result: dict[str, Any] | None) -> dict[str, Any] | None:
    items = (result or {}).get("tracks") or []
    music = [
        t for t in items if isinstance(t, dict) and t.get("videoType") != _UGC_VIDEO
    ]
    if len(music) < _MIN_NON_UGC:
        return result
    return {**(result or {}), "tracks": music}


def _artist_key(track: Track) -> str:
    return str(track.author or "").casefold().strip()
