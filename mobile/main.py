"""Quantis Mobile — бета для Android: Яндекс Музыка и YouTube.

Отдельное маленькое приложение, а не настольный Quantis: тот тянет
aiohttp, qasync, keyring и интерфейс под мышь. Здесь yt-dlp и
yandex-music (чистый Python, кладутся рядом при сборке) и QtMultimedia.

Яндекс играет потоком по прямой ссылке. YouTube сначала качается в кэш:
ссылкам googlevideo нужны заголовки, а QMediaPlayer их не передаёт.
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

# На телефоне FFmpeg-бэкенд Qt открывал поток AAudio, тот сразу отключался
# («stream disconnected»), и так по кругу: трек «играл» без звука. Системный
# MediaPlayer Android играет и файлы, и ссылки сам. Задать до QtMultimedia.
if hasattr(sys, "getandroidapilevel"):
    os.environ.setdefault("QT_MEDIA_BACKEND", "android")

import sources
from android_media import NEXT, PAUSE, PLAY, PREV, SEEK_BASE, MediaControls
from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSettings,
    QStandardPaths,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScroller,
    QSlider,
    QVBoxLayout,
    QWidget,
)
from sources import YANDEX, YOUTUBE, Result

TOKEN_KEY = "yandex/token"
SOURCE_KEY = "search/source"


def _install_ca_bundle() -> None:
    """У Python на Android нет системных сертификатов для OpenSSL.

    Без них любой HTTPS-запрос падает на проверке. Сборка кладёт
    сертификаты в модуль ca_bundle.py (файлы .pem в APK не попадают).
    """
    try:
        from ca_bundle import PEM
    except ImportError:  # на компьютере сертификаты есть и без него
        return
    target = (
        Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.CacheLocation
            )
            or Path.home()
        )
        / "cacert.pem"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="ascii") != PEM:
        target.write_text(PEM, encoding="ascii")
    os.environ["SSL_CERT_FILE"] = str(target)
    os.environ["QUANTIS_CA_FILE"] = str(target)  # для certifi.py рядом


def cache_dir() -> Path:
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.CacheLocation
    )
    path = Path(base or Path.home() / ".cache" / "quantis-mobile") / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
            self.signals.failed.emit(str(exc) or type(exc).__name__)
            return
        self.signals.done.emit(result)


def _fmt(ms: int) -> str:
    seconds = max(0, ms) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


STYLE = """
QWidget { background: #101218; color: #eef0f6; font-size: 16px; }
QLineEdit {
    background: #1c1f28; border: 1px solid #2c3040; border-radius: 12px;
    padding: 12px 14px; min-height: 24px;
}
QPushButton {
    background: #262a36; border: none; border-radius: 12px;
    padding: 12px 16px; min-height: 24px; min-width: 48px;
}
QPushButton:pressed { background: #343a4a; }
QPushButton:disabled { color: #6b7080; }
QPushButton#play { background: #6c5ce7; font-weight: 700; min-width: 72px; }
QPushButton#source { padding: 8px 14px; border-radius: 16px; font-size: 14px; }
QPushButton#source:checked { background: #6c5ce7; color: #ffffff; }
QListWidget { background: transparent; border: none; }
QListWidget::item { padding: 12px 6px; border-bottom: 1px solid #1f2230; }
QListWidget::item:selected { background: #222638; color: #ffffff; }
QLabel#status, QLabel#hint { color: #9aa0b4; font-size: 14px; }
QLabel#now { font-weight: 700; }
QSlider::groove:horizontal { height: 6px; background: #2c3040; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #6c5ce7; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #ffffff; width: 22px; margin: -8px 0; border-radius: 11px;
}
"""


class AccountDialog(QDialog):
    """Вход в Яндекс Музыку по OAuth-токену, как в настольном Quantis."""

    def __init__(self, window: MobileWindow) -> None:
        super().__init__(window)
        self.setWindowTitle("Аккаунт")
        self._window = window
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        title = QLabel("Яндекс Музыка")
        title.setObjectName("now")
        root.addWidget(title)
        hint = QLabel(
            "Вставь OAuth-токен Яндекс Музыки — тот же, что в Quantis на "
            "компьютере. Он хранится только на этом телефоне."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self._token = QLineEdit(window.token)
        self._token.setPlaceholderText("Токен")
        self._token.setEchoMode(QLineEdit.EchoMode.Password)
        root.addWidget(self._token)
        self._status = QLabel()
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        root.addWidget(self._status)
        row = QHBoxLayout()
        self._save = QPushButton("Сохранить")
        self._save.clicked.connect(self._on_save)
        logout = QPushButton("Выйти")
        logout.clicked.connect(self._on_logout)
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        for button in (self._save, logout, close):
            row.addWidget(button, 1)
        root.addLayout(row)
        root.addStretch(1)
        if window.token:
            self._check(window.token)

    def _check(self, token: str) -> None:
        self._save.setEnabled(False)
        self._status.setText("Проверяем токен…")
        self._window.run_job(
            sources.check_yandex_token,
            (token,),
            lambda who: self._on_checked(token, who),
            self._on_failed,
        )

    def _on_save(self) -> None:
        token = self._token.text().strip()
        if token:
            self._check(token)

    def _on_checked(self, token: str, who: str) -> None:
        self._save.setEnabled(True)
        self._window.set_token(token)
        self._status.setText(f"Вход выполнен: {who}")

    def _on_failed(self, text: str) -> None:
        self._save.setEnabled(True)
        self._status.setText(f"Токен не подошёл: {text}")

    def _on_logout(self) -> None:
        self._token.clear()
        self._window.set_token("")
        self._status.setText("Вы вышли из аккаунта")


class MobileWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Quantis")
        self._settings = QSettings()
        self._pool = QThreadPool.globalInstance()
        self._jobs: set[Job] = set()  # держим ссылки, пока задачи идут
        self._results: list[Result] = []
        self._current = -1
        self._seeking = False
        self.token = str(self._settings.value(TOKEN_KEY, "") or "")

        # Плашка в шторке Android; на компьютере — пустышка.
        self._controls = MediaControls()
        self._controls_timer = QTimer(self)
        self._controls_timer.setInterval(400)
        self._controls_timer.timeout.connect(self._poll_controls)
        self._controls_timer.start()

        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._player.setAudioOutput(self._audio)
        self._player.positionChanged.connect(self._on_position)
        self._player.durationChanged.connect(self._on_duration)
        self._player.playbackStateChanged.connect(self._sync_play_button)
        self._player.mediaStatusChanged.connect(self._on_media_status)
        self._player.errorOccurred.connect(
            lambda _err, text: self._set_status(f"Ошибка плеера: {text}")
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        search_row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("Трек или артист")
        self._query.returnPressed.connect(self._search)
        search_row.addWidget(self._query, 1)
        self._search_btn = QPushButton("Найти")
        self._search_btn.clicked.connect(self._search)
        search_row.addWidget(self._search_btn)
        root.addLayout(search_row)

        source_row = QHBoxLayout()
        self._sources = QButtonGroup(self)
        self._yandex_btn = QPushButton("Яндекс")
        self._youtube_btn = QPushButton("YouTube")
        for button, source in (
            (self._yandex_btn, YANDEX),
            (self._youtube_btn, YOUTUBE),
        ):
            button.setObjectName("source")
            button.setCheckable(True)
            button.setProperty("source", source)
            self._sources.addButton(button)
            source_row.addWidget(button)
        self._sources.buttonClicked.connect(self._on_source_clicked)
        source_row.addStretch(1)
        account = QPushButton("Аккаунт")
        account.setObjectName("source")
        account.clicked.connect(lambda: AccountDialog(self).showMaximized())
        source_row.addWidget(account)
        root.addLayout(source_row)

        self._status = QLabel()
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        root.addWidget(self._status)

        self._list = QListWidget()
        self._list.setWordWrap(True)
        self._list.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Свайп с инерцией: без QScroller список на телефоне не листается пальцем.
        QScroller.grabGesture(
            self._list.viewport(), QScroller.ScrollerGestureType.TouchGesture
        )
        self._list.itemClicked.connect(lambda item: self._play_at(self._list.row(item)))
        root.addWidget(self._list, 1)

        self._now = QLabel("Ничего не играет")
        self._now.setObjectName("now")
        self._now.setWordWrap(True)
        root.addWidget(self._now)

        seek_row = QHBoxLayout()
        self._pos_label = QLabel("0:00")
        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.sliderPressed.connect(lambda: setattr(self, "_seeking", True))
        self._seek.sliderReleased.connect(self._on_seek_released)
        self._len_label = QLabel("0:00")
        seek_row.addWidget(self._pos_label)
        seek_row.addWidget(self._seek, 1)
        seek_row.addWidget(self._len_label)
        root.addLayout(seek_row)

        controls = QHBoxLayout()
        self._prev_btn = QPushButton("⏮")
        self._prev_btn.clicked.connect(lambda: self._play_at(self._current - 1))
        self._play_btn = QPushButton("▶")
        self._play_btn.setObjectName("play")
        self._play_btn.clicked.connect(self._toggle)
        self._next_btn = QPushButton("⏭")
        self._next_btn.clicked.connect(lambda: self._play_at(self._current + 1))
        for button in (self._prev_btn, self._play_btn, self._next_btn):
            controls.addWidget(button, 1)
        root.addLayout(controls)

        saved = str(self._settings.value(SOURCE_KEY, "") or "")
        self._select_source(saved or (YANDEX if self.token else YOUTUBE))
        self._sync_play_button()
        # Импорт yt-dlp и yandex-music на телефоне — секунды: заранее, в фоне.
        self.run_job(sources.warm_up, (), lambda _: None, lambda _: None)

    # --- фоновые задачи ---------------------------------------------------

    def run_job(self, fn, args, on_done, on_fail) -> None:
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
        self._status.setText(text)

    # --- источник и аккаунт ----------------------------------------------

    @property
    def source(self) -> str:
        button = self._sources.checkedButton()
        return button.property("source") if button else YOUTUBE

    def _select_source(self, source: str) -> None:
        if source == YANDEX and not self.token:
            source = YOUTUBE
        button = self._yandex_btn if source == YANDEX else self._youtube_btn
        button.setChecked(True)
        self._settings.setValue(SOURCE_KEY, source)
        self._set_status(
            "Поиск в Яндекс Музыке"
            if source == YANDEX
            else "Поиск на YouTube"
            + ("" if self.token else " · войди в Яндекс в «Аккаунте»")
        )

    def _on_source_clicked(self, button: QPushButton) -> None:
        source = button.property("source")
        if source == YANDEX and not self.token:
            self._select_source(YOUTUBE)
            self._set_status("Чтобы искать в Яндексе, войди в «Аккаунте»")
            return
        self._select_source(source)

    def set_token(self, token: str) -> None:
        self.token = token
        self._settings.setValue(TOKEN_KEY, token)
        self._select_source(YANDEX if token else YOUTUBE)

    # --- поиск ------------------------------------------------------------

    def _search(self) -> None:
        query = self._query.text().strip()
        if not query:
            return
        self._search_btn.setEnabled(False)
        self._set_status("Ищем…")
        if self.source == YANDEX:
            fn, args = sources.search_yandex, (self.token, query)
        else:
            fn, args = sources.search_youtube, (query,)
        self.run_job(fn, args, self._on_results, self._on_search_failed)

    def _on_results(self, results: list[Result]) -> None:
        self._search_btn.setEnabled(True)
        self._results = results
        self._current = -1
        self._list.clear()
        for result in results:
            self._list.addItem(QListWidgetItem(result.label))
        self._set_status(f"Найдено: {len(results)}" if results else "Ничего не нашлось")

    def _on_search_failed(self, text: str) -> None:
        self._search_btn.setEnabled(True)
        self._set_status(f"Поиск не удался: {text}")

    # --- воспроизведение --------------------------------------------------

    def _play_at(self, row: int) -> None:
        if not 0 <= row < len(self._results):
            return
        self._current = row
        self._list.setCurrentRow(row)
        result = self._results[row]
        self._now.setText(f"{result.title}\n{result.artist}")
        self._sync_controls()
        self._player.stop()
        self._set_status("Загружаем трек…")
        self.run_job(
            sources.resolve,
            (result, self.token, cache_dir()),
            lambda url, r=row: self._on_resolved(r, url),
            self._set_status,
        )

    def _on_resolved(self, row: int, url: str) -> None:
        if row != self._current:
            return  # пока искали ссылку, выбрали другой трек
        self._set_status("")
        self._player.setSource(QUrl(url))
        self._player.play()
        self._prefetch(row + 1)

    def _prefetch(self, row: int) -> None:
        """YouTube качается долго — следующий трек готовим, пока играет этот.

        Ссылки Яндекса живут недолго, а получаются за доли секунды: их не
        готовим заранее.
        """
        if 0 <= row < len(self._results) and self._results[row].source == YOUTUBE:
            self.run_job(
                sources.fetch_youtube,
                (self._results[row].track_id, cache_dir()),
                lambda _: None,
                lambda _: None,
            )

    def _toggle(self) -> None:
        if self._is_playing():
            self._player.pause()
        elif self._player.source().isEmpty():
            self._play_at(max(0, self._current))
        else:
            self._player.play()

    def _is_playing(self) -> bool:
        return self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def _sync_play_button(self, *_: object) -> None:
        self._play_btn.setText("⏸" if self._is_playing() else "▶")
        self._sync_controls()

    def _sync_controls(self) -> None:
        if not 0 <= self._current < len(self._results):
            return
        result = self._results[self._current]
        self._controls.update(
            result.title,
            result.artist,
            self._is_playing(),
            self._player.position(),
            self._player.duration() or result.duration * 1000,
        )

    def _poll_controls(self) -> None:
        """Кнопки плашки: Java складывает нажатия в очередь, забираем здесь."""
        while (command := self._controls.poll()) >= 0:
            if command == PLAY and not self._is_playing():
                self._toggle()
            elif command == PAUSE:
                self._player.pause()
            elif command == NEXT:
                self._play_at(self._current + 1)
            elif command == PREV:
                self._play_at(self._current - 1)
            elif command >= SEEK_BASE:
                self._player.setPosition(command - SEEK_BASE)
                self._sync_controls()

    def _on_media_status(self, status: QMediaPlayer.MediaStatus) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._play_at(self._current + 1)

    def _on_position(self, ms: int) -> None:
        if not self._seeking:
            self._seek.setValue(ms)
        self._pos_label.setText(_fmt(ms))

    def _on_duration(self, ms: int) -> None:
        self._seek.setRange(0, max(0, ms))
        self._len_label.setText(_fmt(ms))
        self._sync_controls()

    def _on_seek_released(self) -> None:
        self._seeking = False
        self._player.setPosition(self._seek.value())
        self._sync_controls()

    def closeEvent(self, event) -> None:
        self._controls.release()
        super().closeEvent(event)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("QuantisMobile")
    app.setOrganizationName("ReallyFun")
    app.setStyleSheet(STYLE)
    _install_ca_bundle()  # после QApplication: нужен путь к кэшу приложения
    window = MobileWindow()
    if hasattr(sys, "getandroidapilevel"):
        window.showMaximized()
    else:
        window.resize(420, 820)  # проверка на компьютере: размер телефона
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
