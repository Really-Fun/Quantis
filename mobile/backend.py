"""Контроллер для QML: поиск, очередь, воспроизведение, аккаунт.

Интерфейс (qml/) только показывает свойства и зовёт слоты; вся работа —
здесь и в sources.py / stream_proxy.py / android_media.py. Сеть — в пуле
потоков (Job), результат возвращается в главный поток сигналом.
"""

from __future__ import annotations

import json
import logging
import random
import time
import traceback
import wave
from dataclasses import asdict
from urllib.parse import quote

import art
import lyrics
import offline
import sources
from android_media import NEXT, PAUSE, PLAY, PREV, SEEK_BASE, MediaControls
from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from sources import SOUNDCLOUD, YANDEX, YOUTUBE, Result
from stream_proxy import StreamProxy

log = logging.getLogger(__name__)

TOKEN_KEY = "yandex/token"
SOURCE_KEY = "search/source"
HISTORY_KEY = "library/history"
LIKES_KEY = "library/likes"
QUERIES_KEY = "search/recent"
# Кэш медиатеки Яндекса: показываем сразу, обновляем в фоне.
YANDEX_LIKED_KEY = "yandex/liked"
YANDEX_PLAYLISTS_KEY = "yandex/playlists"
LIBRARY_REFRESH_S = 300
PLAYLISTS_KEY = "library/playlists"  # свои плейлисты на телефоне
HOME_CHART_KEY = "home/chart"
HOME_RELEASES_KEY = "home/releases"
HOME_REFRESH_S = 1800
COLLECTIONS_LIMIT = 40
HISTORY_LIMIT = 30
QUERIES_LIMIT = 8
REPEAT_OFF, REPEAT_ALL, REPEAT_ONE = 0, 1, 2


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    """Функция в пуле потоков: сеть не должна держать интерфейс."""

    def __init__(self, fn, *args) -> None:
        super().__init__()
        self.signals = _Signals()
        self._fn = fn
        self._args = args

    def run(self) -> None:
        try:
            result = self._fn(*self._args)
        except Exception as exc:
            traceback.print_exc()
            self._emit(self.signals.failed, str(exc) or type(exc).__name__)
            return
        self._emit(self.signals.done, result)

    @staticmethod
    def _emit(signal, value) -> None:
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # приложение закрылось, пока задача шла: ответ некому


class TrackModel(QAbstractListModel):
    TitleRole = Qt.ItemDataRole.UserRole + 1
    ArtistRole = TitleRole + 1
    DurationRole = TitleRole + 2
    SourceRole = TitleRole + 3
    CoverRole = TitleRole + 4
    OfflineRole = TitleRole + 5  # трек скачан на телефон

    # Общая проверка «скачан ли» для всех списков (ставит AppController).
    is_offline = staticmethod(lambda _result: False)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[Result] = []

    @Slot(int, result=str)
    def titleAt(self, row: int) -> str:
        return self._items[row].title if 0 <= row < len(self._items) else ""

    @Slot(int, result=str)
    def artistAt(self, row: int) -> str:
        return self._items[row].artist if 0 <= row < len(self._items) else ""

    @Slot(int, result=str)
    def coverAt(self, row: int) -> str:
        """Обложка строки для QML (url-encoded, как роль cover)."""
        if 0 <= row < len(self._items) and self._items[row].cover:
            return quote(self._items[row].cover, safe="")
        return ""

    def refresh_offline(self) -> None:
        if self._items:
            self.dataChanged.emit(
                self.index(0), self.index(len(self._items) - 1), [self.OfflineRole]
            )

    def items(self) -> list[Result]:
        return list(self._items)

    def set_items(self, items: list[Result]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()
        self.countChanged.emit()

    countChanged = Signal()

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._items)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._items)

    def roleNames(self) -> dict[int, QByteArray]:
        return {
            self.TitleRole: QByteArray(b"title"),
            self.ArtistRole: QByteArray(b"artist"),
            self.DurationRole: QByteArray(b"duration"),
            self.SourceRole: QByteArray(b"source"),
            self.CoverRole: QByteArray(b"cover"),
            self.OfflineRole: QByteArray(b"offline"),
        }

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        item = self._items[index.row()]
        if role == self.TitleRole:
            return item.title
        if role == self.ArtistRole:
            return item.artist
        if role == self.DurationRole:
            return item.duration
        if role == self.SourceRole:
            return item.source
        if role == self.CoverRole:
            return quote(item.cover, safe="") if item.cover else ""
        if role == self.OfflineRole:
            return TrackModel.is_offline(item)
        return None


class Collection(QObject):
    """Открытая страница: альбом, исполнитель, плейлист или чарт. У каждой —
    своя модель треков (listName для playFrom и меню), так страницы в разных
    вкладках не мешают друг другу."""

    changed = Signal()

    def __init__(self, name: str, title: str, parent: QObject) -> None:
        super().__init__(parent)
        self._name = name
        self._tracks = TrackModel(self)
        self._loading = True
        self._error = ""
        self._title = title
        self._subtitle = ""
        self._cover = ""
        self._albums: list[dict] = []

    def fill(self, data: dict) -> None:
        self._tracks.set_items(data.get("tracks", []))
        self._title = data.get("title") or self._title
        self._subtitle = data.get("subtitle", "")
        tracks = data.get("tracks", [])
        # Нет своей обложки (чарт, плейлист из треков) — обложка первого трека.
        self._cover = data.get("cover") or next((t.cover for t in tracks if t.cover), "")
        self._albums = data.get("albums", [])
        self._loading = False
        self.changed.emit()

    def fail(self, text: str) -> None:
        self._loading = False
        self._error = f"Не удалось загрузить: {text}"
        self.changed.emit()

    @Property(str, constant=True)
    def listName(self) -> str:
        return self._name

    @Property(QObject, constant=True)
    def tracks(self) -> TrackModel:
        return self._tracks

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._loading

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(str, notify=changed)
    def title(self) -> str:
        return self._title

    @Property(str, notify=changed)
    def subtitle(self) -> str:
        return self._subtitle

    @Property(str, notify=changed)
    def cover(self) -> str:
        return self._cover

    @Property("QVariantList", notify=changed)
    def albums(self) -> list[dict]:
        return self._albums


class AppController(QObject):
    sourceChanged = Signal()
    statusChanged = Signal()
    searchingChanged = Signal()
    accountChanged = Signal()
    trackChanged = Signal()
    playStateChanged = Signal()
    positionChanged = Signal()
    durationChanged = Signal()
    modeChanged = Signal()
    paletteChanged = Signal()
    queriesChanged = Signal()
    likesChanged = Signal()
    waveChanged = Signal()
    sleepChanged = Signal()
    yandexLibraryChanged = Signal()
    remoteChanged = Signal()
    downloadsChanged = Signal()
    lyricsChanged = Signal()
    playlistsChanged = Signal()
    searchExtrasChanged = Signal()
    homeChanged = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._settings = QSettings()
        self._pool = QThreadPool.globalInstance()
        self._jobs: set[Job] = set()
        self._token = str(self._settings.value(TOKEN_KEY, "") or "")
        self._account = ""
        self._status = ""
        self._searching = False
        self._results = TrackModel(self)
        # История: что реально заиграло, новое — первым; хранится в QSettings.
        self._history = TrackModel(self)
        self._history.set_items(self._load_history())
        self._queries: list[str] = self._load_queries()
        self._liked = TrackModel(self)
        self._liked.set_items(self._load_tracks(LIKES_KEY))
        # Медиатека Яндекса: «Мне нравится» и свои плейлисты (из кэша, потом
        # из сети) и открытый плейлист — remote.
        self._yandex_liked = TrackModel(self)
        self._yandex_liked.set_items(self._load_tracks(YANDEX_LIKED_KEY))
        self._yandex_playlists = self._load_playlists()
        self._library_jobs = 0
        self._library_at = -LIBRARY_REFRESH_S
        self._remote = TrackModel(self)
        self._remote_loading = False
        self._remote_error = ""
        self._remote_gen = 0
        # Скачанное: файлы и каталог — offline.OfflineStore; качаем по одному
        # (Яндекс не любит параллельные запросы с одного токена).
        self._offline = offline.OfflineStore()
        TrackModel.is_offline = staticmethod(self._offline.has)
        self._downloaded = TrackModel(self)
        self._downloaded.set_items(self._offline.tracks())
        self._dl_queue: list[Result] = []
        self._dl_active: Result | None = None
        self._dl_failed = 0
        # Свои плейлисты: [{"id", "name", "tracks": [Result…]}], открытый — в
        # модели "playlist".
        self._playlists: list[dict] = self._load_local_playlists()
        self._playlist_model = TrackModel(self)
        self._playlist_id = ""
        # Открытые страницы альбомов, исполнителей, плейлистов (по listName).
        self._collections: dict[str, Collection] = {}
        self._collection_seq = 0
        # Поиск Яндекса по всему: кроме треков — исполнители, альбомы, плейлисты.
        self._search_extras: dict = {}
        # Главная: чарт и новые релизы Яндекса (кэш, обновление раз в 30 минут).
        self._home_chart = TrackModel(self)
        self._home_chart.set_items(self._load_tracks(HOME_CHART_KEY))
        self._home_releases = self._load_json(HOME_RELEASES_KEY)
        self._home_at = -HOME_REFRESH_S
        # Текст песни текущего трека: грузится, только пока открыт экран текста.
        self._lyrics_open = False
        self._lyrics_for: Result | None = None
        self._lyrics = lyrics.Lyrics()
        self._lyrics_state = "idle"  # idle | loading | ready | none | error
        self.trackChanged.connect(self._lyrics_track_changed)
        # Очередь для экрана «Очередь» — та же, что играет.
        self._queue_model = TrackModel(self)
        # «Моя волна»: сессия, имя волны и признак, что очередь — волна.
        self._wave: wave.WaveSession | None = None
        self._wave_name = ""
        self._wave_loading = False
        self._wave_more_pending = False
        self._started_at: tuple[Result, int] | None = (
            None  # трек и позиция для feedback
        )
        # Таймер сна: секунд до паузы (0 — выключен) или «до конца трека».
        self._sleep_left = 0
        self._sleep_end_of_track = False
        self._sleep_timer = QTimer(self)
        self._sleep_timer.setInterval(1000)
        self._sleep_timer.timeout.connect(self._sleep_tick)
        self._queue: list[Result] = []
        self._current = -1
        self._loading = False
        # Пока ссылка готовится, плашке и службе сообщаем «играет»: службу
        # переднего плана Android даёт запустить только с открытого
        # приложения, а без неё свёрнутое приложение замораживается.
        self._wants_play = False
        self._palette = art.DEFAULT
        self._shuffle = False
        self._repeat = REPEAT_ALL
        saved = str(self._settings.value(SOURCE_KEY, "") or "")
        self._source = saved or (YANDEX if self._token else YOUTUBE)
        if self._source == YANDEX and not self._token:
            self._source = YOUTUBE

        self._proxy = StreamProxy()
        self._controls = MediaControls()
        self._animations = self._controls.animations_enabled()
        self._controls_timer = QTimer(self)
        self._controls_timer.setInterval(400)
        self._controls_timer.timeout.connect(self._poll_controls)
        self._controls_timer.start()

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.positionChanged.connect(lambda _ms: self.positionChanged.emit())
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._on_play_state)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(
            lambda _err, text: self._set_status(f"Ошибка плеера: {text}")
        )
        # Импорт yt-dlp и yandex-music на телефоне — секунды: заранее, в фоне.
        self._run(sources.warm_up, (), lambda _: None, lambda _: None)
        if self._token:
            self.checkAccount()

    # --- фоновые задачи ---------------------------------------------------

    def _run(self, fn, args, on_done, on_fail) -> None:
        job = Job(fn, *args)
        self._jobs.add(job)
        job.setAutoDelete(False)

        def finish(handler, value) -> None:
            self._jobs.discard(job)
            handler(value)

        job.signals.done.connect(lambda value: finish(on_done, value))
        job.signals.failed.connect(lambda text: finish(on_fail, text))
        self._pool.start(job)

    def _flash(self, text: str) -> None:
        """Короткая подсказка о действии: сама исчезает через 2,5 с."""
        self._set_status(text)
        QTimer.singleShot(2500, lambda: self._status == text and self._set_status(""))

    def _set_status(self, text: str) -> None:
        if text != self._status:
            self._status = text
            self.statusChanged.emit()

    # --- свойства для QML -------------------------------------------------

    @Property(str, notify=sourceChanged)
    def source(self) -> str:
        return self._source

    @Property(str, notify=statusChanged)
    def status(self) -> str:
        return self._status

    @Property(bool, notify=searchingChanged)
    def searching(self) -> bool:
        return self._searching

    @Property(QObject, constant=True)
    def results(self) -> TrackModel:
        return self._results

    @Property(QObject, constant=True)
    def history(self) -> TrackModel:
        return self._history

    @Property("QStringList", notify=queriesChanged)
    def recentQueries(self) -> list[str]:
        return list(self._queries)

    @Property(QObject, constant=True)
    def liked(self) -> TrackModel:
        return self._liked

    @Property(QObject, constant=True)
    def yandexLiked(self) -> TrackModel:
        return self._yandex_liked

    @Property("QVariantList", notify=yandexLibraryChanged)
    def yandexPlaylists(self) -> list[dict]:
        return self._yandex_playlists

    @Property(bool, notify=yandexLibraryChanged)
    def yandexLibraryLoading(self) -> bool:
        return self._library_jobs > 0

    @Property(QObject, constant=True)
    def remote(self) -> TrackModel:
        return self._remote

    @Property(bool, notify=remoteChanged)
    def remoteLoading(self) -> bool:
        return self._remote_loading

    @Property(str, notify=remoteChanged)
    def remoteError(self) -> str:
        return self._remote_error

    @Property(QObject, constant=True)
    def downloaded(self) -> TrackModel:
        return self._downloaded

    @Property(int, notify=downloadsChanged)
    def downloadsPending(self) -> int:
        return len(self._dl_queue) + (self._dl_active is not None)

    @Property(str, notify=downloadsChanged)
    def downloadingTitle(self) -> str:
        return self._dl_active.title if self._dl_active else ""

    @Property(str, notify=downloadsChanged)
    def offlineSize(self) -> str:
        size = self._offline.total_bytes()
        if size >= 1024**3:
            return f"{size / 1024**3:.1f} ГБ".replace(".", ",")
        return f"{round(size / 1024**2)} МБ"

    @Property("QVariantList", notify=lyricsChanged)
    def lyricsLines(self) -> list[dict]:
        return self._lyrics.lines

    @Property(bool, notify=lyricsChanged)
    def lyricsSynced(self) -> bool:
        return self._lyrics.synced

    @Property(str, notify=lyricsChanged)
    def lyricsSource(self) -> str:
        return self._lyrics.source

    @Property(str, notify=lyricsChanged)
    def lyricsState(self) -> str:
        return self._lyrics_state

    @Property("QVariantList", notify=playlistsChanged)
    def localPlaylists(self) -> list[dict]:
        """Для QML: id, название, число треков, обложка первого трека."""
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "count": len(p["tracks"]),
                "cover": quote(p["tracks"][0].cover, safe="")
                if p["tracks"] and p["tracks"][0].cover else "",
            }
            for p in self._playlists
        ]

    @Property(QObject, constant=True)
    def playlist(self) -> TrackModel:
        return self._playlist_model

    @Property(str, notify=playlistsChanged)
    def playlistName(self) -> str:
        found = self._find_playlist(self._playlist_id)
        return found["name"] if found else ""

    @Property("QVariantList", notify=searchExtrasChanged)
    def searchArtists(self) -> list[dict]:
        return self._search_extras.get("artists", [])

    @Property("QVariantList", notify=searchExtrasChanged)
    def searchAlbums(self) -> list[dict]:
        return self._search_extras.get("albums", [])

    @Property("QVariantList", notify=searchExtrasChanged)
    def searchPlaylists(self) -> list[dict]:
        return self._search_extras.get("playlists", [])

    @Property("QVariantMap", notify=searchExtrasChanged)
    def searchBest(self) -> dict:
        return self._search_extras.get("best") or {}

    @Property(QObject, constant=True)
    def homeChart(self) -> TrackModel:
        return self._home_chart

    @Property("QVariantList", notify=homeChanged)
    def homeReleases(self) -> list[dict]:
        return self._home_releases

    @Property(QObject, constant=True)
    def queue(self) -> TrackModel:
        return self._queue_model

    @Property(int, notify=trackChanged)
    def queueIndex(self) -> int:
        return self._current

    @Property(bool, notify=likesChanged)
    def currentLiked(self) -> bool:
        track = self._track()
        return track is not None and self._is_liked(track)

    @Property(bool, notify=waveChanged)
    def waveActive(self) -> bool:
        return self._wave is not None

    @Property(str, notify=waveChanged)
    def waveName(self) -> str:
        return self._wave_name

    @Property(bool, notify=waveChanged)
    def waveLoading(self) -> bool:
        return self._wave_loading

    @Property("QVariantList", constant=True)
    def moods(self) -> list[dict]:
        return [
            {"name": m.name, "seeds": ",".join(m.seeds), "color": m.color}
            for m in wave.MOODS
        ]

    @Property(int, notify=sleepChanged)
    def sleepLeft(self) -> int:
        return self._sleep_left

    @Property(bool, notify=sleepChanged)
    def sleepEndOfTrack(self) -> bool:
        return self._sleep_end_of_track

    # --- любимое ----------------------------------------------------------

    @staticmethod
    def _contains(model: TrackModel, result: Result) -> bool:
        key = (result.source, result.track_id)
        return any((r.source, r.track_id) == key for r in model.items())

    def _is_liked(self, result: Result) -> bool:
        """Лайк на телефоне или (у треков Яндекса) в «Мне нравится» аккаунта."""
        return self._contains(self._liked, result) or (
            result.source == YANDEX and self._contains(self._yandex_liked, result)
        )

    def _toggle_like(self, result: Result) -> None:
        like = not self._is_liked(result)
        key = (result.source, result.track_id)
        items = [r for r in self._liked.items() if (r.source, r.track_id) != key]
        if like:
            items.insert(0, result)
        self._liked.set_items(items)
        self._save_tracks(LIKES_KEY, items)
        if result.source == YANDEX and self._token:
            # «♡» у трека Яндекса — и лайк в аккаунте: сразу в списке, запрос в фоне.
            remote = [r for r in self._yandex_liked.items() if (r.source, r.track_id) != key]
            if like:
                remote.insert(0, result)
            self._yandex_liked.set_items(remote)
            self._save_tracks(YANDEX_LIKED_KEY, remote)
            self._run(
                sources.yandex_set_like,
                (self._token, result.track_id, like),
                lambda _: None,
                lambda text: self._flash(f"Яндекс не сохранил лайк: {text}"),
            )
        self.likesChanged.emit()

    @Slot()
    def toggleLike(self) -> None:
        track = self._track()
        if track is not None:
            self._toggle_like(track)

    # --- действия со строками любого списка -------------------------------

    def _model(self, name: str) -> TrackModel | None:
        return {
            "results": self._results,
            "history": self._history,
            "liked": self._liked,
            "queue": self._queue_model,
            "yandexLiked": self._yandex_liked,
            "remote": self._remote,
            "downloaded": self._downloaded,
            "playlist": self._playlist_model,
            "homeChart": self._home_chart,
        }.get(name) or (
            self._collections[name].tracks if name in self._collections else None
        )

    def _item(self, name: str, row: int) -> Result | None:
        model = self._model(name)
        items = model.items() if model is not None else []
        return items[row] if 0 <= row < len(items) else None

    @Slot(str, int)
    def playFrom(self, name: str, row: int) -> None:
        """Касание трека в списке: очередью становится весь список."""
        if name == "queue":
            self._play_at(row)
            return
        model = self._model(name)
        if model is not None and 0 <= row < model.count:
            self._stop_wave()
            self._set_queue(model.items())
            self._play_at(row)

    @Slot(str, int)
    def playNextFrom(self, name: str, row: int) -> None:
        item = self._item(name, row)
        if item is None:
            return
        if self._track() is None:
            self._set_queue([item])
            self._play_at(0)
            return
        queue = list(self._queue)
        queue.insert(self._current + 1, item)
        self._set_queue(queue)
        self._flash("Сыграет следующим")

    @Slot(str, int)
    def enqueueFrom(self, name: str, row: int) -> None:
        item = self._item(name, row)
        if item is None:
            return
        self._set_queue([*self._queue, item])
        if self._track() is None:
            self._play_at(len(self._queue) - 1)
        else:
            self._flash("Добавлено в конец очереди")

    @Slot(str, int)
    def toggleLikeFrom(self, name: str, row: int) -> None:
        item = self._item(name, row)
        if item is not None:
            self._toggle_like(item)

    @Slot(str, int, result=bool)
    def isLikedFrom(self, name: str, row: int) -> bool:
        item = self._item(name, row)
        return item is not None and self._is_liked(item)

    def _set_queue(self, items: list[Result]) -> None:
        self._queue = list(items)
        self._queue_model.set_items(self._queue)

    # --- скачанное --------------------------------------------------------

    def _dl_key(self, result: Result) -> tuple[str, str]:
        return (result.source, result.track_id)

    def _is_downloading(self, result: Result) -> bool:
        key = self._dl_key(result)
        active = self._dl_active is not None and self._dl_key(self._dl_active) == key
        return active or any(self._dl_key(r) == key for r in self._dl_queue)

    def _enqueue_downloads(self, items: list[Result]) -> int:
        added = 0
        for item in items:
            if item.source == YANDEX and not self._token:
                continue
            if self._offline.has(item) or self._is_downloading(item):
                continue
            self._dl_queue.append(item)
            added += 1
        if added:
            self.downloadsChanged.emit()
            self._next_download()
        return added

    def _next_download(self) -> None:
        if self._dl_active is not None:
            return
        if not self._dl_queue:
            if self._dl_failed:
                self._flash(f"Не скачалось треков: {self._dl_failed}")
                self._dl_failed = 0
            self.downloadsChanged.emit()
            return
        item = self._dl_queue.pop(0)
        self._dl_active = item
        self.downloadsChanged.emit()

        def done(file_name: str) -> None:
            self._offline.add(item, file_name)
            self._dl_active = None
            self._refresh_offline()
            self._next_download()

        def failed(text: str) -> None:
            log.warning("Не скачался %s: %s", item.title, text)
            self._dl_failed += 1
            self._dl_active = None
            self._next_download()

        self._run(self._offline.download, (item, self._token), done, failed)

    def _refresh_offline(self) -> None:
        self._downloaded.set_items(self._offline.tracks())
        for model in (
            self._results, self._history, self._liked, self._queue_model,
            self._yandex_liked, self._remote, self._playlist_model, self._home_chart,
            *(c.tracks for c in self._collections.values()),
        ):
            model.refresh_offline()
        self.downloadsChanged.emit()

    @Slot(str, int)
    def downloadFrom(self, name: str, row: int) -> None:
        item = self._item(name, row)
        if item is None:
            return
        if item.source == YANDEX and not self._token:
            self._flash("Чтобы скачать трек Яндекса, войди в аккаунт")
            return
        if self._enqueue_downloads([item]):
            self._flash("Скачиваем на телефон")

    @Slot(str)
    def downloadAll(self, name: str) -> None:
        model = self._model(name)
        if model is None:
            return
        added = self._enqueue_downloads(model.items())
        self._flash(f"В очереди на скачивание: {added}" if added else "Всё уже скачано")

    @Slot()
    def cancelDownloads(self) -> None:
        """Убрать ожидающие загрузки; текущий трек докачается."""
        if self._dl_queue:
            self._dl_queue.clear()
            self.downloadsChanged.emit()
            self._flash("Остальные загрузки отменены")

    @Slot(str, int)
    def removeDownloadFrom(self, name: str, row: int) -> None:
        item = self._item(name, row)
        if item is not None and self._offline.has(item):
            self._offline.remove(item)
            self._refresh_offline()
            self._flash("Удалено с телефона")

    @Slot(str, int, result=int)
    def downloadStateFrom(self, name: str, row: int) -> int:
        """0 — не скачан, 1 — в очереди или качается, 2 — скачан."""
        item = self._item(name, row)
        if item is None:
            return 0
        if self._offline.has(item):
            return 2
        return 1 if self._is_downloading(item) else 0

    # --- свои плейлисты ----------------------------------------------------

    def _load_local_playlists(self) -> list[dict]:
        try:
            raw = json.loads(str(self._settings.value(PLAYLISTS_KEY, "[]") or "[]"))
            return [
                {"id": str(p["id"]), "name": str(p["name"]),
                 "tracks": [Result(**t) for t in p.get("tracks", [])]}
                for p in raw
            ]
        except (TypeError, ValueError, KeyError):
            return []

    def _save_local_playlists(self) -> None:
        self._settings.setValue(
            PLAYLISTS_KEY,
            json.dumps(
                [{"id": p["id"], "name": p["name"],
                  "tracks": [asdict(t) for t in p["tracks"]]} for p in self._playlists],
                ensure_ascii=False,
            ),
        )
        found = self._find_playlist(self._playlist_id)
        self._playlist_model.set_items(found["tracks"] if found else [])
        self.playlistsChanged.emit()

    def _find_playlist(self, playlist_id: str) -> dict | None:
        return next((p for p in self._playlists if p["id"] == playlist_id), None)

    @Slot(str, result=str)
    def createPlaylist(self, name: str) -> str:
        name = name.strip() or "Новый плейлист"
        playlist_id = f"{int(time.time() * 1000):x}"
        self._playlists.insert(0, {"id": playlist_id, "name": name, "tracks": []})
        self._save_local_playlists()
        return playlist_id

    @Slot(str, str)
    def renamePlaylist(self, playlist_id: str, name: str) -> None:
        found = self._find_playlist(playlist_id)
        if found is not None and name.strip():
            found["name"] = name.strip()
            self._save_local_playlists()

    @Slot(str)
    def deletePlaylist(self, playlist_id: str) -> None:
        self._playlists = [p for p in self._playlists if p["id"] != playlist_id]
        self._save_local_playlists()

    @Slot(str)
    def openLocalPlaylist(self, playlist_id: str) -> None:
        self._playlist_id = playlist_id
        found = self._find_playlist(playlist_id)
        self._playlist_model.set_items(found["tracks"] if found else [])
        self.playlistsChanged.emit()

    @Slot(str, int, str)
    def addToPlaylistFrom(self, name: str, row: int, playlist_id: str) -> None:
        item = self._item(name, row)
        found = self._find_playlist(playlist_id)
        if item is None or found is None:
            return
        key = (item.source, item.track_id)
        if any((t.source, t.track_id) == key for t in found["tracks"]):
            self._flash(f"Уже в «{found['name']}»")
            return
        found["tracks"].append(item)
        self._save_local_playlists()
        self._flash(f"Добавлено в «{found['name']}»")

    @Slot(int)
    def removeFromPlaylist(self, row: int) -> None:
        found = self._find_playlist(self._playlist_id)
        if found is not None and 0 <= row < len(found["tracks"]):
            del found["tracks"][row]
            self._save_local_playlists()

    # --- страницы: альбом, исполнитель, плейлист, чарт ---------------------

    @Slot(str, str, str, result=QObject)
    def openCollection(self, kind: str, ref: str, title: str) -> Collection:
        """kind: album | artist | playlist ("uid:kind") | chart | local | liked."""
        self._collection_seq += 1
        name = f"c{self._collection_seq}"
        page = Collection(name, title, self)
        self._collections[name] = page
        while len(self._collections) > COLLECTIONS_LIMIT:
            self._collections.pop(next(iter(self._collections)))
        token = self._token
        if kind == "local":
            found = self._find_playlist(ref)
            page.fill({"title": found["name"] if found else title,
                       "subtitle": "Плейлист на телефоне",
                       "tracks": found["tracks"] if found else []})
            return page
        if kind == "liked":
            page.fill({"title": "Мне нравится", "subtitle": "Яндекс Музыка",
                       "tracks": self._yandex_liked.items()})
            return page
        if kind in ("album", "artist", "playlist", "chart") and not token:
            page.fail("нужен вход в Яндекс Музыку")
            return page
        if kind == "album":
            fn, args = sources.yandex_album, (token, ref)
        elif kind == "artist":
            fn, args = sources.yandex_artist, (token, ref)
        elif kind == "playlist":
            uid, _, playlist_kind = ref.partition(":")
            fn, args = sources.yandex_playlist_page, (token, uid, playlist_kind)
        elif kind == "chart":
            def fn(t):  # noqa: E306
                return {"title": "Чарт", "subtitle": "Популярное на Яндекс Музыке",
                        "tracks": sources.yandex_chart(t)}
            args = (token,)
        else:
            page.fail(f"неизвестная страница {kind}")
            return page
        self._run(fn, args, page.fill, page.fail)
        return page

    # --- главная ------------------------------------------------------------

    @Slot()
    def refreshHome(self) -> None:
        """Чарт и новые релизы: при открытии главной, не чаще раза в 30 минут."""
        if not self._token or time.monotonic() - self._home_at < HOME_REFRESH_S:
            return
        self._home_at = time.monotonic()
        token = self._token

        def chart_done(items: list[Result]) -> None:
            if token == self._token:
                self._home_chart.set_items(items)
                self._save_tracks(HOME_CHART_KEY, items)

        def releases_done(items: list[dict]) -> None:
            if token == self._token:
                self._home_releases = items
                self._settings.setValue(HOME_RELEASES_KEY, json.dumps(items, ensure_ascii=False))
                self.homeChanged.emit()

        def failed(_text: str) -> None:
            self._home_at = -HOME_REFRESH_S  # в следующий раз попробовать снова

        self._run(sources.yandex_chart, (token,), chart_done, failed)
        self._run(sources.yandex_new_releases, (token,), releases_done, failed)

    def _load_json(self, key: str) -> list[dict]:
        try:
            raw = json.loads(str(self._settings.value(key, "[]") or "[]"))
            return [dict(i) for i in raw if isinstance(i, dict)]
        except (TypeError, ValueError):
            return []

    # --- текст песни -------------------------------------------------------

    @Slot(bool)
    def setLyricsOpen(self, opened: bool) -> None:
        self._lyrics_open = opened
        if opened:
            self._load_lyrics()

    def _lyrics_track_changed(self) -> None:
        if self._lyrics_open:
            self._load_lyrics()

    def _load_lyrics(self) -> None:
        track = self._track()
        if track is None or track is self._lyrics_for:
            return
        self._lyrics_for = track
        self._lyrics = lyrics.Lyrics()
        self._lyrics_state = "loading"
        self.lyricsChanged.emit()

        def done(found: lyrics.Lyrics) -> None:
            if self._lyrics_for is track:
                self._lyrics = found
                self._lyrics_state = "ready" if found.lines else "none"
                self.lyricsChanged.emit()

        def failed(_text: str) -> None:
            if self._lyrics_for is track:
                self._lyrics_for = None  # открыть ещё раз — попробовать снова
                self._lyrics_state = "error"
                self.lyricsChanged.emit()

        self._run(lyrics.fetch, (track, self._token), done, failed)

    # --- медиатека Яндекса ------------------------------------------------

    @Slot()
    def refreshYandexLibrary(self) -> None:
        """Открыта медиатека: обновить, если с прошлого раза прошло 5 минут."""
        if time.monotonic() - self._library_at > LIBRARY_REFRESH_S:
            self._refresh_library()

    def _refresh_library(self) -> None:
        """«Мне нравится» и плейлисты из сети; кэш виден, пока идёт запрос."""
        if not self._token or self._library_jobs:
            return
        self._library_at = time.monotonic()
        token = self._token
        self._library_jobs = 2
        self.yandexLibraryChanged.emit()

        def finish() -> None:
            self._library_jobs = max(0, self._library_jobs - 1)
            self.yandexLibraryChanged.emit()

        def liked_done(items: list[Result]) -> None:
            if token == self._token:
                self._yandex_liked.set_items(items)
                self._save_tracks(YANDEX_LIKED_KEY, items)
            finish()

        def playlists_done(items: list[dict]) -> None:
            if token == self._token:
                self._yandex_playlists = items
                self._settings.setValue(
                    YANDEX_PLAYLISTS_KEY, json.dumps(items, ensure_ascii=False)
                )
            finish()

        def failed(text: str) -> None:
            self._flash(f"Медиатека Яндекса не обновилась: {text}")
            finish()

        self._run(sources.yandex_liked, (token,), liked_done, failed)
        self._run(sources.yandex_playlists, (token,), playlists_done, failed)

    @Slot(str, str)
    def openPlaylist(self, uid: str, kind: str) -> None:
        """Загрузить плейлист в remote; ответ на прошлый запрос — отбросить."""
        self._remote_gen += 1
        gen = self._remote_gen
        self._remote.set_items([])
        self._remote_loading = True
        self._remote_error = ""
        self.remoteChanged.emit()

        def done(items: list[Result]) -> None:
            if gen == self._remote_gen:
                self._remote.set_items(items)
                self._remote_loading = False
                self.remoteChanged.emit()

        def failed(text: str) -> None:
            if gen == self._remote_gen:
                self._remote_loading = False
                self._remote_error = f"Не удалось загрузить: {text}"
                self.remoteChanged.emit()

        self._run(sources.yandex_playlist, (self._token, uid, kind), done, failed)

    def _load_playlists(self) -> list[dict]:
        try:
            raw = json.loads(str(self._settings.value(YANDEX_PLAYLISTS_KEY, "[]") or "[]"))
            return [dict(item) for item in raw if isinstance(item, dict)]
        except (TypeError, ValueError):
            return []

    def _clear_yandex_library(self) -> None:
        self._yandex_liked.set_items([])
        self._yandex_playlists = []
        self._settings.remove(YANDEX_LIKED_KEY)
        self._settings.remove(YANDEX_PLAYLISTS_KEY)
        self.yandexLibraryChanged.emit()
        self._home_chart.set_items([])
        self._home_releases = []
        self._home_at = -HOME_REFRESH_S
        self._settings.remove(HOME_CHART_KEY)
        self._settings.remove(HOME_RELEASES_KEY)
        self.homeChanged.emit()

    # --- моя волна --------------------------------------------------------

    @Slot(str, str)
    def startWave(self, seeds: str, name: str) -> None:
        if not self._token:
            self._set_status(
                "Моя волна — из Яндекс Музыки: войди в аккаунт в «Медиатеке»"
            )
            return
        session = wave.WaveSession(self._token)
        seed_tuple = tuple(x for x in seeds.split(",") if x) or wave.MY_WAVE.seeds
        self._wave_loading = True
        self.waveChanged.emit()

        def done(tracks: list[Result]) -> None:
            self._wave = session
            self._wave_name = name or wave.MY_WAVE.name
            self._wave_loading = False
            self.waveChanged.emit()
            self._set_queue(tracks)
            self._play_at(0)

        def failed(text: str) -> None:
            self._wave_loading = False
            self.waveChanged.emit()
            self._set_status(text)

        self._run(session.start, (seed_tuple,), done, failed)

    def _stop_wave(self) -> None:
        if self._wave is not None:
            self._wave = None
            self._wave_name = ""
            self.waveChanged.emit()

    def _wave_feedback_end(self) -> None:
        """Яндексу — дослушали трек или пропустили (по позиции)."""
        if self._wave is None or self._started_at is None:
            return
        result, _ = self._started_at
        played = self._player.position() / 1000
        self._run(
            self._wave.finished,
            (result, played, result.duration),
            lambda _: None,
            lambda _: None,
        )
        self._started_at = None

    def _wave_top_up(self) -> None:
        """Осталось два трека — догружаем следующую порцию волны."""
        if self._wave is None or self._wave_more_pending:
            return
        if self._current < len(self._queue) - 2:
            return
        self._wave_more_pending = True
        session = self._wave

        def done(tracks: list[Result]) -> None:
            self._wave_more_pending = False
            if session is self._wave and tracks:
                self._set_queue([*self._queue, *tracks])

        def failed(_text: str) -> None:
            self._wave_more_pending = False

        self._run(session.more, (list(self._queue),), done, failed)

    # --- таймер сна -------------------------------------------------------

    @Slot(int)
    def setSleep(self, minutes: int) -> None:
        """minutes > 0 — пауза через столько минут; -1 — в конце трека; 0 — выкл."""
        self._sleep_end_of_track = minutes < 0
        self._sleep_left = max(0, minutes) * 60
        if self._sleep_left:
            self._sleep_timer.start()
        else:
            self._sleep_timer.stop()
        self.sleepChanged.emit()

    def _sleep_tick(self) -> None:
        self._sleep_left = max(0, self._sleep_left - 1)
        if self._sleep_left == 0:
            self._sleep_timer.stop()
            if self._is_playing():
                self.toggle()
        self.sleepChanged.emit()

    # --- история и недавние запросы --------------------------------------

    def _load_history(self) -> list[Result]:
        return self._load_tracks(HISTORY_KEY)[:HISTORY_LIMIT]

    def _load_tracks(self, key: str) -> list[Result]:
        try:
            raw = json.loads(str(self._settings.value(key, "[]") or "[]"))
            return [Result(**item) for item in raw]
        except (TypeError, ValueError):
            return []

    def _save_tracks(self, key: str, items: list[Result]) -> None:
        self._settings.setValue(
            key, json.dumps([asdict(r) for r in items], ensure_ascii=False)
        )

    def _remember(self, result: Result) -> None:
        items = [
            r
            for r in self._history.items()
            if (r.source, r.track_id) != (result.source, result.track_id)
        ]
        items.insert(0, result)
        items = items[:HISTORY_LIMIT]
        self._history.set_items(items)
        self._save_tracks(HISTORY_KEY, items)

    def _load_queries(self) -> list[str]:
        try:
            raw = json.loads(str(self._settings.value(QUERIES_KEY, "[]") or "[]"))
            return [str(q) for q in raw][:QUERIES_LIMIT]
        except (TypeError, ValueError):
            return []

    def _remember_query(self, query: str) -> None:
        queries = [q for q in self._queries if q.casefold() != query.casefold()]
        queries.insert(0, query)
        self._queries = queries[:QUERIES_LIMIT]
        self._settings.setValue(
            QUERIES_KEY, json.dumps(self._queries, ensure_ascii=False)
        )
        self.queriesChanged.emit()

    @Slot(int)
    def playHistory(self, row: int) -> None:
        self.playFrom("history", row)

    @Property(bool, notify=accountChanged)
    def loggedIn(self) -> bool:
        return bool(self._token)

    @Property(str, notify=accountChanged)
    def account(self) -> str:
        return self._account

    def _track(self) -> Result | None:
        if 0 <= self._current < len(self._queue):
            return self._queue[self._current]
        return None

    @Property(bool, notify=trackChanged)
    def hasTrack(self) -> bool:
        return self._track() is not None

    @Property(str, notify=trackChanged)
    def title(self) -> str:
        track = self._track()
        return track.title if track else ""

    @Property(str, notify=trackChanged)
    def artist(self) -> str:
        track = self._track()
        return track.artist if track else ""

    @Property(str, notify=trackChanged)
    def trackSource(self) -> str:
        track = self._track()
        return track.source if track else ""

    @Property(str, notify=trackChanged)
    def cover(self) -> str:
        """Адрес обложки для QML: image://art/cover/… (пусто — нет обложки)."""
        track = self._track()
        return quote(track.cover, safe="") if track and track.cover else ""

    @Property(QColor, notify=paletteChanged)
    def accent(self) -> QColor:
        return self._palette.accent

    @Property(QColor, notify=paletteChanged)
    def accent2(self) -> QColor:
        return self._palette.accent2

    @Property(QColor, notify=paletteChanged)
    def deep(self) -> QColor:
        return self._palette.deep

    @Property(QColor, notify=paletteChanged)
    def glow(self) -> QColor:
        return self._palette.glow

    @Property(QColor, notify=paletteChanged)
    def accentText(self) -> QColor:
        return self._palette.accent_text

    @Property(bool, constant=True)
    def animations(self) -> bool:
        """Системные анимации включены: иначе пластинка и аврора стоят."""
        return self._animations

    @Property(bool, notify=playStateChanged)
    def playing(self) -> bool:
        return self._is_playing() or self._wants_play

    @Property(bool, notify=playStateChanged)
    def loading(self) -> bool:
        return self._loading

    @Property(int, notify=positionChanged)
    def position(self) -> int:
        return int(self._player.position())

    @Property(int, notify=durationChanged)
    def duration(self) -> int:
        track = self._track()
        return int(self._player.duration() or (track.duration * 1000 if track else 0))

    @Property(bool, notify=modeChanged)
    def shuffle(self) -> bool:
        return self._shuffle

    @Property(int, notify=modeChanged)
    def repeatMode(self) -> int:
        return self._repeat

    # --- источник и аккаунт ----------------------------------------------

    @Slot(str)
    def setSource(self, source: str) -> None:
        if source == YANDEX and not self._token:
            self._set_status("Чтобы искать в Яндексе, войди в аккаунт в «Медиатеке»")
            return
        if source != self._source:
            self._source = source
            self._settings.setValue(SOURCE_KEY, source)
            self.sourceChanged.emit()

    @Slot(str)
    def saveToken(self, token: str) -> None:
        token = token.strip()
        if not token:
            return
        self._account = "Проверяем токен…"
        self.accountChanged.emit()
        self._run(
            sources.check_yandex_token,
            (token,),
            lambda who: self._on_account(token, who),
            lambda text: self._on_account_failed(text),
        )

    @Slot()
    def checkAccount(self) -> None:
        if self._token:
            self._run(
                sources.check_yandex_token,
                (self._token,),
                lambda who: self._on_account(self._token, who),
                lambda text: self._on_account_failed(text),
            )

    def _on_account(self, token: str, who: str) -> None:
        if token != self._token:
            self._clear_yandex_library()  # другой аккаунт — чужой кэш не показываем
        self._token = token
        self._settings.setValue(TOKEN_KEY, token)
        self._account = who
        self.accountChanged.emit()
        self.setSource(YANDEX)
        self._refresh_library()
        self.refreshHome()

    def _on_account_failed(self, text: str) -> None:
        if text == sources.OFFLINE:
            # Без сети токен не проверить, но и плохим он от этого не стал:
            # вход остаётся, скачанное играет, проверим снова через 30 с.
            self._account = "Нет сети — вход проверим позже"
            QTimer.singleShot(30_000, self.checkAccount)
        else:
            self._account = f"Токен не подошёл: {text}"
        self.accountChanged.emit()

    @Slot()
    def logout(self) -> None:
        self._token = ""
        self._settings.setValue(TOKEN_KEY, "")
        self._clear_yandex_library()
        self._account = ""
        self.accountChanged.emit()
        self.setSource(YOUTUBE)

    # --- поиск ------------------------------------------------------------

    @Slot(str)
    def search(self, query: str) -> None:
        query = query.strip()
        if not query:
            return
        self._searching = True
        self.searchingChanged.emit()
        self._set_status("")
        self._remember_query(query)
        if self._source == YANDEX:
            fn, args = sources.search_yandex_all, (self._token, query)
        elif self._source == SOUNDCLOUD:
            fn, args = sources.search_soundcloud, (query,)
        else:
            fn, args = sources.search_youtube, (query,)
        self._run(fn, args, self._on_results, self._on_search_failed)

    def _on_results(self, results) -> None:
        self._searching = False
        self.searchingChanged.emit()
        extras: dict = {}
        if isinstance(results, dict):  # Яндекс: поиск по всему
            extras = {k: v for k, v in results.items() if k != "tracks"}
            results = results["tracks"]
        self._results.set_items(results)
        self._search_extras = extras
        self.searchExtrasChanged.emit()
        empty = not results and not any(extras.get(k) for k in ("artists", "albums", "playlists"))
        self._set_status("Ничего не нашлось" if empty else "")

    def _on_search_failed(self, text: str) -> None:
        self._searching = False
        self.searchingChanged.emit()
        self._set_status(f"Поиск не удался: {text}")

    # --- воспроизведение --------------------------------------------------

    @Slot(int)
    def playResult(self, row: int) -> None:
        self.playFrom("results", row)

    def _play_at(self, row: int) -> None:
        if not 0 <= row < len(self._queue):
            return
        self._wave_feedback_end()
        self._current = row
        self._wants_play = True
        self._loading = True
        self._player.stop()
        self.trackChanged.emit()
        self.likesChanged.emit()
        self.playStateChanged.emit()
        self.durationChanged.emit()
        self._sync_controls()
        self._wave_top_up()
        result = self._queue[row]
        self._load_palette(result)
        local = self._offline.path(result)
        if local is not None:  # скачан — играем файл, сеть не нужна
            QTimer.singleShot(
                0, lambda r=row: self._on_resolved(r, QUrl.fromLocalFile(str(local)).toString())
            )
            return
        self._run(
            sources.resolve,
            (result, self._token, self._proxy),
            lambda url, r=row: self._on_resolved(r, url),
            self._on_resolve_failed,
        )

    def _load_palette(self, result: Result) -> None:
        """Цвета из обложки: обложка качается в фоне, палитра — по готовности."""

        def work() -> art.Palette:
            return art.palette_from(art.load_cover(result.cover))

        def done(palette: art.Palette) -> None:
            if self._track() is result:
                self._palette = palette
                self.paletteChanged.emit()

        self._run(work, (), done, lambda _: None)

    def _on_resolved(self, row: int, url: str) -> None:
        if row != self._current:
            return  # пока искали ссылку, выбрали другой трек
        self._loading = False
        self._set_status("")
        self._remember(self._queue[row])
        if self._wave is not None:
            self._started_at = (self._queue[row], 0)
            self._run(
                self._wave.started, (self._queue[row],), lambda _: None, lambda _: None
            )
        self._player.setSource(QUrl(url))
        self._player.play()
        self._prefetch(self._next_index(manual=True))

    def _on_resolve_failed(self, text: str) -> None:
        self._loading = False
        self._wants_play = False
        self._set_status(text)
        self.playStateChanged.emit()
        self._sync_controls()

    def _prefetch(self, row: int | None) -> None:
        """Ссылку YouTube разбирать секунды — для следующего трека заранее."""
        if (
            row is not None
            and self._queue[row].source == YOUTUBE
            and not self._offline.has(self._queue[row])
        ):
            self._run(
                sources.youtube_stream,
                (self._queue[row].track_id,),
                lambda _: None,
                lambda _: None,
            )

    def _next_index(self, *, manual: bool) -> int | None:
        count = len(self._queue)
        if count == 0:
            return None
        if self._repeat == REPEAT_ONE and not manual:
            return self._current
        if self._shuffle and count > 1:
            choices = [i for i in range(count) if i != self._current]
            return random.choice(choices)
        following = self._current + 1
        if following < count:
            return following
        if self._wave is not None:
            return None  # волна догрузится, по кругу не идём
        return 0 if self._repeat == REPEAT_ALL else None

    @Slot()
    def toggle(self) -> None:
        if self._is_playing():
            self._wants_play = False
            self._player.pause()
        elif self._track() is None:
            return
        elif self._player.source().isEmpty():
            self._play_at(self._current)
        else:
            self._wants_play = True
            self._player.play()
        self.playStateChanged.emit()

    @Slot()
    def next(self) -> None:
        row = self._next_index(manual=True)
        if row is not None:
            self._play_at(row)

    @Slot()
    def previous(self) -> None:
        # Как в плеерах: больше 3 с от начала — к началу этого же трека.
        if self._player.position() > 3000:
            self._player.setPosition(0)
            self._sync_controls()
        elif self._current > 0:
            self._play_at(self._current - 1)

    @Slot(int)
    def seek(self, ms: int) -> None:
        self._player.setPosition(max(0, ms))
        self._sync_controls()

    @Slot()
    def toggleShuffle(self) -> None:
        self._shuffle = not self._shuffle
        self.modeChanged.emit()

    @Slot()
    def cycleRepeat(self) -> None:
        self._repeat = (self._repeat + 1) % 3
        self.modeChanged.emit()

    def _is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _on_play_state(self, *_: object) -> None:
        self.playStateChanged.emit()
        self._sync_controls()

    def _on_duration(self, *_: object) -> None:
        self.durationChanged.emit()
        self._sync_controls()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self._sleep_end_of_track:  # таймер «до конца трека»
                self.setSleep(0)
                self._wants_play = False
                self.playStateChanged.emit()
                self._sync_controls()
                return
            row = self._next_index(manual=False)
            if row is None:
                self._wants_play = False
                self.playStateChanged.emit()
                self._sync_controls()
            else:
                self._play_at(row)

    # --- плашка в шторке --------------------------------------------------

    def _sync_controls(self) -> None:
        track = self._track()
        if track is None:
            return
        self._controls.update(
            track.title,
            track.artist,
            self.playing,
            self._player.position(),
            self.duration,
        )

    def _poll_controls(self) -> None:
        """Кнопки плашки: Java складывает нажатия в очередь, забираем здесь."""
        while (command := self._controls.poll()) >= 0:
            if command == PLAY and not self._is_playing():
                self.toggle()
            elif command == PAUSE and self._is_playing():
                self.toggle()
            elif command == NEXT:
                self.next()
            elif command == PREV:
                self.previous()
            elif command >= SEEK_BASE:
                self.seek(command - SEEK_BASE)

    def shutdown(self) -> None:
        self._controls.release()
        self._proxy.close()
