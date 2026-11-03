"""Контроллер для QML: поиск, очередь, воспроизведение, аккаунт.

Интерфейс (qml/) только показывает свойства и зовёт слоты; вся работа —
здесь и в sources.py / stream_proxy.py / android_media.py. Сеть — в пуле
потоков (Job), результат возвращается в главный поток сигналом.
"""

from __future__ import annotations

import random
import traceback

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
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from sources import YANDEX, YOUTUBE, Result
from stream_proxy import StreamProxy

TOKEN_KEY = "yandex/token"
SOURCE_KEY = "search/source"
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

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._items: list[Result] = []

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
        return None


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
        self._queue: list[Result] = []
        self._current = -1
        self._loading = False
        # Пока ссылка готовится, плашке и службе сообщаем «играет»: службу
        # переднего плана Android даёт запустить только с открытого
        # приложения, а без неё свёрнутое приложение замораживается.
        self._wants_play = False
        self._shuffle = False
        self._repeat = REPEAT_ALL
        saved = str(self._settings.value(SOURCE_KEY, "") or "")
        self._source = saved or (YANDEX if self._token else YOUTUBE)
        if self._source == YANDEX and not self._token:
            self._source = YOUTUBE

        self._proxy = StreamProxy()
        self._controls = MediaControls()
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
        self._token = token
        self._settings.setValue(TOKEN_KEY, token)
        self._account = who
        self.accountChanged.emit()
        self.setSource(YANDEX)

    def _on_account_failed(self, text: str) -> None:
        self._account = f"Токен не подошёл: {text}"
        self.accountChanged.emit()

    @Slot()
    def logout(self) -> None:
        self._token = ""
        self._settings.setValue(TOKEN_KEY, "")
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
        if self._source == YANDEX:
            fn, args = sources.search_yandex, (self._token, query)
        else:
            fn, args = sources.search_youtube, (query,)
        self._run(fn, args, self._on_results, self._on_search_failed)

    def _on_results(self, results: list[Result]) -> None:
        self._searching = False
        self.searchingChanged.emit()
        self._results.set_items(results)
        self._set_status("" if results else "Ничего не нашлось")

    def _on_search_failed(self, text: str) -> None:
        self._searching = False
        self.searchingChanged.emit()
        self._set_status(f"Поиск не удался: {text}")

    # --- воспроизведение --------------------------------------------------

    @Slot(int)
    def playResult(self, row: int) -> None:
        """Нажатие на трек в выдаче: очередью становится вся выдача."""
        items = self._results.items()
        if 0 <= row < len(items):
            self._queue = items
            self._play_at(row)

    def _play_at(self, row: int) -> None:
        if not 0 <= row < len(self._queue):
            return
        self._current = row
        self._wants_play = True
        self._loading = True
        self._player.stop()
        self.trackChanged.emit()
        self.playStateChanged.emit()
        self.durationChanged.emit()
        self._sync_controls()
        result = self._queue[row]
        self._run(
            sources.resolve,
            (result, self._token, self._proxy),
            lambda url, r=row: self._on_resolved(r, url),
            self._on_resolve_failed,
        )

    def _on_resolved(self, row: int, url: str) -> None:
        if row != self._current:
            return  # пока искали ссылку, выбрали другой трек
        self._loading = False
        self._set_status("")
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
        if row is not None and self._queue[row].source == YOUTUBE:
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
