"""Источники треков беты: YouTube и SoundCloud (yt-dlp), Яндекс Музыка (yandex-music).

Все функции блокирующие: их вызывают из пула потоков, а не из интерфейса.
resolve() отдаёт адрес для QMediaPlayer: прямую ссылку Яндекса или адрес
локального прокси для YouTube (ссылкам googlevideo нужны заголовки, которых
QMediaPlayer не передаёт — их добавляет stream_proxy). Оба играют сразу.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

SEARCH_LIMIT = 20
OFFLINE = "Нет сети"  # текст ошибки, по которому интерфейс узнаёт офлайн
YANDEX, YOUTUBE, SOUNDCLOUD = "yandex", "youtube", "soundcloud"

T = TypeVar("T")


@dataclass(frozen=True)
class Result:
    source: str
    track_id: str
    title: str
    artist: str
    duration: int  # секунды, 0 — неизвестно
    cover: str = ""  # https-адрес обложки, "" — нет

    @property
    def label(self) -> str:
        minutes, seconds = divmod(self.duration, 60)
        length = f"  ·  {minutes}:{seconds:02d}" if self.duration else ""
        return f"{self.title}\n{self.artist}{length}"


def warm_up() -> None:
    """Импорт тяжёлых библиотек заранее: на телефоне это секунды."""
    import yandex_music  # noqa: F401
    import yt_dlp  # noqa: F401


# --- YouTube ----------------------------------------------------------------

_AUDIO_FORMAT = (
    "ba[protocol=https][ext=m4a]/ba[protocol=https]/bestaudio[protocol=https]/bestaudio"
)
# Клиент android быстрее, но для многих видео отвечает «формат недоступен»:
# после первого такого отказа за сессию его больше не пробуем (−1,2 с на трек).
_android_client_ok = True
_stream_locks: dict[str, threading.Lock] = {}
_stream_locks_guard = threading.Lock()
_streams: dict[str, YoutubeStream] = {}


@dataclass(frozen=True)
class YoutubeStream:
    """Прямая ссылка googlevideo и заголовки, без которых она не отвечает."""

    url: str
    headers: dict[str, str]
    content_type: str
    size: int | None
    expires: float


def search_youtube(query: str) -> list[Result]:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{SEARCH_LIMIT}:{query}", download=False)
    results = []
    for entry in (info or {}).get("entries") or []:
        video_id = entry.get("id")
        if not video_id:
            continue
        results.append(
            Result(
                source=YOUTUBE,
                track_id=video_id,
                title=entry.get("title") or video_id,
                artist=entry.get("channel") or entry.get("uploader") or "",
                duration=int(entry.get("duration") or 0),
                # hqdefault есть у любого видео; квадрат вырезает art.py.
                cover=f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            )
        )
    return results


def _youtube_attempts() -> list[tuple[str, dict]]:
    common = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": _AUDIO_FORMAT,
    }
    attempts = []
    if _android_client_ok:
        attempts.append(
            (
                "android",
                {
                    **common,
                    "extractor_args": {
                        "youtube": {
                            "player_client": ["android"],
                            "skip": ["hls", "dash", "translated_subs"],
                            "player_skip": ["webpage", "configs"],
                        }
                    },
                },
            )
        )
    attempts.append(("default", common))
    return attempts


def _expires(url: str) -> float:
    """Срок ссылки из её параметра expire, с запасом в 5 минут."""
    from urllib.parse import parse_qs, urlparse

    try:
        expire = float(parse_qs(urlparse(url).query)["expire"][0])
    except (KeyError, IndexError, ValueError):
        return time.time() + 1800
    return expire - 300


def youtube_stream(video_id: str, *, fresh: bool = False) -> YoutubeStream:
    """Ссылка на звук без скачивания; живая ссылка берётся из кэша.

    fresh=True — googlevideo ответил 403, ссылку нужно получить заново.
    """
    global _android_client_ok
    import yt_dlp

    with _stream_locks_guard:
        lock = _stream_locks.setdefault(video_id, threading.Lock())
    with lock:  # трек и его предзагрузка не разбирают одно видео вдвоём
        cached = _streams.get(video_id)
        if cached is not None and not fresh and cached.expires > time.time():
            return cached
        url = f"https://www.youtube.com/watch?v={video_id}"
        error: Exception | None = None
        for name, opts in _youtube_attempts():
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as exc:
                error = exc
                if name == "android" and "format is not available" in str(exc):
                    _android_client_ok = False
                continue
            stream_url = info.get("url")
            if not stream_url:
                continue
            ext = info.get("ext") or "m4a"
            stream = YoutubeStream(
                url=stream_url,
                headers={
                    str(k): str(v) for k, v in (info.get("http_headers") or {}).items()
                },
                content_type="audio/webm" if ext == "webm" else "audio/mp4",
                size=info.get("filesize") or None,
                expires=_expires(stream_url),
            )
            _streams[video_id] = stream
            return stream
        if error is not None and "not a bot" in str(error):
            raise RuntimeError(
                "YouTube просит подтвердить, что вы не бот. Попробуйте позже "
                "или найдите трек в Яндексе."
            )
        raise RuntimeError(f"YouTube не отдал звук: {error}")


# --- SoundCloud -------------------------------------------------------------

# Поиск и ссылки — через yt-dlp, он сам берёт client_id с сайта. Звук у
# SoundCloud почти всегда HLS (m3u8, AAC): MediaPlayer Android и FFmpeg на
# компьютере играют его сами, заголовки не нужны.
_SC_FORMAT = "bestaudio[protocol=https]/bestaudio[protocol=http]/bestaudio"


def soundcloud_url(track_id: str) -> str:
    return f"https://api.soundcloud.com/tracks/soundcloud%3Atracks%3A{track_id}"


def _soundcloud_cover(entry: dict) -> str:
    for thumb in entry.get("thumbnails") or []:
        if thumb.get("id") == "t500x500":
            return str(thumb.get("url") or "")
    url = str(entry.get("thumbnail") or "")
    return url.replace("-original.", "-t500x500.") if url.startswith("https://") else ""


def search_soundcloud(query: str) -> list[Result]:
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"scsearch{SEARCH_LIMIT}:{query}", download=False)
    results = []
    for entry in (info or {}).get("entries") or []:
        track_id = str(entry.get("id") or "")
        if not track_id.isdigit():
            continue
        results.append(
            Result(
                source=SOUNDCLOUD,
                track_id=track_id,
                title=entry.get("title") or track_id,
                artist=entry.get("uploader") or "",
                duration=int(entry.get("duration") or 0),
                cover=_soundcloud_cover(entry),
            )
        )
    return results


def soundcloud_stream(track_id: str) -> str:
    """Адрес звука для плеера (подписанный, живёт недолго — берём перед игрой)."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "format": _SC_FORMAT}
    info = None
    for attempt in range(2):  # из этой сети TLS к SoundCloud иногда рвётся
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(soundcloud_url(track_id), download=False)
            break
        except Exception as exc:
            raise_soundcloud_error(exc, retry=attempt == 0)
    url = (info or {}).get("url")
    if not url:
        raise RuntimeError("SoundCloud не отдал звук")
    return url


def raise_soundcloud_error(exc: Exception, *, retry: bool = False) -> None:
    """Понятный текст вместо отчёта yt-dlp; при обрыве TLS — вернуться и повторить."""
    text = str(exc)
    if "DRM" in text:
        raise RuntimeError(
            "SoundCloud защищает этот трек (DRM) — его не сыграть. "
            "Поищи его в Яндексе или на YouTube."
        ) from exc
    if retry and ("SSL" in text or "timed out" in text):
        return
    raise RuntimeError(f"SoundCloud не отдал звук: {text.removeprefix('ERROR: ')}") from exc


def soundcloud_download_options(outtmpl: str) -> dict:
    # Для файла лучше цельный mp3, если он есть; HLS yt-dlp склеит сам.
    return {
        "quiet": True, "no_warnings": True, "noprogress": True, "outtmpl": outtmpl,
        "format": "bestaudio[protocol=https]/bestaudio[protocol=http]/bestaudio",
    }


# --- Яндекс Музыка ----------------------------------------------------------

# Как в настольном Quantis: download-info с одного токена Яндекс отдаёт по
# одному запросу за раз (429 «Concurrency limit»), поэтому запросы идут по
# очереди, а при отказе повторяются с паузой и разбросом.
_RATE_LIMIT_RETRIES = (0.5, 1.0, 2.0, 3.0)
_yandex_lock = threading.Lock()
_clients: dict[str, object] = {}


def _rate_limited(exc: BaseException) -> bool:
    text = str(exc)
    return "(429)" in text or "Concurrency limit" in text


def _yandex(call: Callable[[], T]) -> T:
    with _yandex_lock:
        for delay in (*_RATE_LIMIT_RETRIES, None):
            try:
                return call()
            except Exception as exc:
                if delay is None or not _rate_limited(exc):
                    raise
                time.sleep(delay * random.uniform(0.8, 1.3))
    raise AssertionError("недостижимо")


def _client(token: str):
    from yandex_music import Client

    client = _clients.get(token)
    if client is None:
        client = _clients[token] = Client(token)
    return client


def _network_error(exc: BaseException) -> bool:
    from yandex_music.exceptions import NetworkError, TimedOutError

    return isinstance(exc, (NetworkError, TimedOutError, OSError))


def check_yandex_token(token: str) -> str:
    """Логин аккаунта; бросает исключение, если токен не подходит.

    Нет сети — RuntimeError(OFFLINE): токен тут ни при чём.
    """
    from yandex_music import Client

    try:
        client = _yandex(lambda: Client(token).init())
    except Exception as exc:
        if _network_error(exc):
            raise RuntimeError(OFFLINE) from exc
        raise
    account = client.me.account if client.me else None
    login = (account.login or account.display_name) if account else ""
    plus = bool(client.me and client.me.plus and client.me.plus.has_plus)
    return f"{login or 'аккаунт'}{' · Плюс' if plus else ' · без Плюса'}"


def search_yandex(token: str, query: str) -> list[Result]:
    client = _client(token)
    found = _yandex(lambda: client.search(query, type_="track"))
    tracks = found.tracks.results if found and found.tracks else []
    results = []
    for track in tracks:
        result = yandex_result(track)
        if result is not None:
            results.append(result)
        if len(results) >= SEARCH_LIMIT:
            break
    return results


LIBRARY_LIMIT = 1000  # треков из «Мне нравится» и одного плейлиста
_TRACKS_BATCH = 250  # id в одном запросе /tracks


def _full_tracks(client, ids: list[str]) -> list:
    """Полные треки по id, пачками: у «Мне нравится» в ответе только id."""
    tracks = []
    for start in range(0, len(ids), _TRACKS_BATCH):
        chunk = ids[start : start + _TRACKS_BATCH]
        tracks += _yandex(lambda chunk=chunk: client.tracks(chunk)) or []
    return tracks


def _results(tracks) -> list[Result]:
    return [r for r in map(yandex_result, tracks) if r is not None]


def yandex_liked(token: str) -> list[Result]:
    """«Мне нравится» аккаунта, новые — первыми."""
    client = _client(token)
    likes = _yandex(client.users_likes_tracks)
    ids = [
        f"{t.id}:{t.album_id}" if t.album_id else str(t.id)
        for t in (likes.tracks if likes else [])[:LIBRARY_LIMIT]
    ]
    return _results(_full_tracks(client, ids))


def _album_info(album) -> dict | None:
    if album is None or not album.id:
        return None
    artist = ", ".join(a.name for a in (album.artists or []) if a.name)
    year = f" · {album.year}" if album.year else ""
    return {
        "id": str(album.id),
        "title": album.title or "Альбом",
        "subtitle": f"{artist}{year}",
        "cover": _yandex_cover(album.cover_uri or album.og_image or ""),
    }


def _artist_info(artist) -> dict | None:
    if artist is None or not artist.id:
        return None
    uri = (artist.cover.uri if artist.cover else "") or artist.og_image or ""
    return {"id": str(artist.id), "name": artist.name or "Исполнитель",
            "cover": _yandex_cover(uri)}


def _clean(items) -> list[dict]:
    return [i for i in items if i is not None]


def search_yandex_all(token: str, query: str) -> dict:
    """Поиск по всему: треки (Result), исполнители, альбомы, плейлисты и
    лучший результат {"type": artist|album|playlist|track, "item": …}."""
    client = _client(token)
    found = _yandex(lambda: client.search(query, type_="all"))

    def part(name):
        block = getattr(found, name, None) if found else None
        return block.results if block and block.results else []

    tracks = _results(part("tracks"))[:SEARCH_LIMIT]
    artists = _clean(map(_artist_info, part("artists")))
    albums = _clean(map(_album_info, part("albums")))
    playlists = _clean(_playlist_info(p, liked=True) for p in part("playlists"))
    best = None
    if found and found.best and found.best.result is not None:
        kind, item = found.best.type, found.best.result
        info = {
            "artist": _artist_info, "album": _album_info,
            "playlist": lambda p: _playlist_info(p, liked=True),
        }.get(kind)
        if info is not None:
            best = {"type": kind, "item": info(item)}
        elif kind == "track" and tracks:
            best = {"type": "track", "item": {"index": 0}}
    if best is not None and best["item"] is None:
        best = None
    return {"tracks": tracks, "artists": artists, "albums": albums,
            "playlists": playlists, "best": best}


def yandex_artist(token: str, artist_id: str) -> dict:
    """Исполнитель: имя, фото, популярные треки и альбомы (новые — первыми)."""
    client = _client(token)
    brief = _yandex(lambda: client.artists_brief_info(artist_id))
    direct = _yandex(lambda: client.artists_direct_albums(artist_id, page_size=50))
    albums = (direct.albums if direct else None) or (brief.albums if brief else []) or []
    albums = sorted(albums, key=lambda a: a.year or 0, reverse=True)
    artist = _artist_info(brief.artist if brief else None) or {"name": "", "cover": ""}
    return {
        "title": artist["name"],
        "subtitle": "Исполнитель",
        "cover": artist["cover"],
        "tracks": _results(brief.popular_tracks if brief else []),
        "albums": _clean(map(_album_info, albums)),
    }


def yandex_album(token: str, album_id: str) -> dict:
    client = _client(token)
    album = _yandex(lambda: client.albums_with_tracks(album_id))
    info = _album_info(album) or {"title": "", "subtitle": "", "cover": ""}
    tracks = [t for volume in (album.volumes or []) for t in volume] if album else []
    return {"title": info["title"], "subtitle": info["subtitle"], "cover": info["cover"],
            "tracks": _results(tracks), "albums": []}


def yandex_playlist_page(token: str, uid: str, kind: str) -> dict:
    client = _client(token)
    playlist = _yandex(lambda: client.users_playlists(kind, uid))
    info = _playlist_info(playlist, liked=True) or {"title": "", "owner": "", "cover": ""}
    return {"title": info["title"], "subtitle": info.get("owner") or "Плейлист",
            "cover": info["cover"], "tracks": yandex_playlist(token, uid, kind), "albums": []}


def yandex_chart(token: str) -> list[Result]:
    """Чарт Яндекса: самые популярные треки сейчас (до 50)."""
    chart = _yandex(_client(token).chart)
    shorts = (chart.chart.tracks if chart and chart.chart else [])[:50]
    return _results(s.track for s in shorts)


def yandex_new_releases(token: str) -> list[dict]:
    client = _client(token)
    landing = _yandex(client.new_releases)
    ids = (landing.new_releases if landing else [])[:20]
    albums = _yandex(lambda: client.albums(ids)) if ids else []
    return _clean(map(_album_info, albums))


def yandex_set_like(token: str, track_id: str, liked: bool) -> None:
    """Поставить или снять лайк в «Мне нравится» аккаунта."""
    client = _client(token)
    call = client.users_likes_tracks_add if liked else client.users_likes_tracks_remove
    _yandex(lambda: call(track_id))


def _playlist_info(playlist, *, liked: bool) -> dict | None:
    if playlist is None or playlist.kind is None or playlist.owner is None:
        return None
    cover = playlist.cover
    uri = ""
    if cover is not None:
        uri = cover.uri or (cover.items_uri[0] if cover.items_uri else "")
    owner = playlist.owner
    return {
        "uid": str(owner.uid),
        "kind": str(playlist.kind),
        "title": playlist.title or "Без названия",
        "count": int(playlist.track_count or 0),
        "cover": _yandex_cover(uri or playlist.og_image or ""),
        "liked": liked,  # чужой плейлист из лайков, а не свой
        "owner": (owner.name or owner.login or "") if liked else "",
    }


def yandex_playlists(token: str) -> list[dict]:
    """Свои плейлисты аккаунта, потом лайкнутые чужие: uid, kind, название,
    число треков, обложка, liked, owner."""
    client = _client(token)
    own = [_playlist_info(p, liked=False) for p in _yandex(client.users_playlists_list) or []]
    likes = _yandex(client.users_likes_playlists) or []
    liked = [_playlist_info(like.playlist, liked=True) for like in likes]
    seen, found = set(), []
    for info in own + liked:
        if info is not None and (info["uid"], info["kind"]) not in seen:
            seen.add((info["uid"], info["kind"]))
            found.append(info)
    return found


def yandex_playlist(token: str, uid: str, kind: str) -> list[Result]:
    """Треки плейлиста по порядку; если треки пришли без данных — дозапрос."""
    client = _client(token)
    playlist = _yandex(lambda: client.users_playlists(kind, uid))
    shorts = (playlist.tracks if playlist else [])[:LIBRARY_LIMIT]
    if all(s.track is not None for s in shorts):
        return _results(s.track for s in shorts)
    ids = [f"{s.id}:{s.album_id}" if s.album_id else str(s.id) for s in shorts]
    return _results(_full_tracks(client, ids))


def yandex_result(track) -> Result | None:
    """Трек yandex-music → Result; недоступный (нет прав, удалён) — None."""
    if track is None or track.available is False or not track.id:
        return None
    title = track.title or str(track.id)
    if track.version:
        title = f"{title} ({track.version})"
    artist = ", ".join(a.name for a in (track.artists or []) if a.name)
    return Result(
        source=YANDEX,
        track_id=str(track.id),
        title=title,
        artist=artist,
        duration=int(track.duration_ms or 0) // 1000,
        cover=_yandex_cover(track.cover_uri or track.og_image or ""),
    )


def _yandex_cover(uri: str, size: int = 400) -> str:
    """avatars.yandex.net/…/%% → https-адрес квадратной обложки size×size."""
    if not uri:
        return ""
    return "https://" + uri.replace("%%", f"{size}x{size}")


def _best_download_info(infos: list) -> object | None:
    """Полный трек, а не превью; mp3 предпочтительнее, затем битрейт."""

    def rank(item) -> tuple:
        codec = str(getattr(item, "codec", "") or "").lower()
        return (
            0 if getattr(item, "preview", False) else 1,
            2 if codec == "mp3" else (1 if codec in ("aac", "mp4") else 0),
            int(getattr(item, "bitrate_in_kbps", 0) or 0),
        )

    return max(infos, key=rank) if infos else None


def yandex_link(token: str, track_id: str) -> tuple[str, str]:
    """Прямая ссылка на полный трек и кодек (mp3, aac…)."""
    client = _client(token)
    tracks = _yandex(lambda: client.tracks([track_id]))
    if not tracks:
        raise RuntimeError("Трек не найден в Яндекс Музыке")
    infos = _yandex(lambda: tracks[0].get_download_info()) or []
    chosen = _best_download_info(list(infos))
    if chosen is None:
        raise RuntimeError("Яндекс не отдал ссылку на трек")
    if getattr(chosen, "preview", False):
        raise RuntimeError("Полный трек доступен только с Плюсом — есть лишь превью")
    codec = str(getattr(chosen, "codec", "") or "mp3").lower()
    return _yandex(chosen.get_direct_link), codec


def resolve_yandex(token: str, track_id: str) -> str:
    """Прямая ссылка на звук: QMediaPlayer играет её потоком, без скачивания."""
    return yandex_link(token, track_id)[0]


def youtube_download_options(outtmpl: str) -> list[dict]:
    """Настройки yt-dlp для скачивания звука в файл (те же клиенты, что и поток)."""
    return [
        {**opts, "outtmpl": outtmpl, "noprogress": True}
        for _name, opts in _youtube_attempts()
    ]


# --- общее ------------------------------------------------------------------


def resolve(result: Result, token: str, proxy) -> str:
    """Адрес для QMediaPlayer: https:// Яндекса или http://127.0.0.1 прокси."""
    if result.source == YANDEX:
        return resolve_yandex(token, result.track_id)
    if result.source == SOUNDCLOUD:
        return soundcloud_stream(result.track_id)
    youtube_stream(result.track_id)  # ошибка YouTube — сейчас, а не в плеере
    return proxy.url_for(result.track_id)
