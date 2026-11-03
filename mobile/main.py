"""Quantis Mobile — бета для Android: поиск на YouTube и воспроизведение.

Отдельное маленькое приложение, а не настольный Quantis: тот тянет
aiohttp, qasync, keyring и интерфейс под мышь. Здесь только yt-dlp
(чистый Python, кладётся рядом при сборке) и QtMultimedia.

Трек сначала скачивается в кэш приложения, затем играет как файл:
ссылкам googlevideo нужны заголовки, а QMediaPlayer их не передаёт.
"""

from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QStandardPaths,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication,
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

SEARCH_LIMIT = 20


def _install_ca_bundle() -> None:
    """У Python на Android нет системных сертификатов для OpenSSL.

    Без них любой HTTPS-запрос yt-dlp падает на проверке. Сборка кладёт
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


@dataclass(frozen=True)
class Result:
    video_id: str
    title: str
    channel: str
    duration: int  # секунды, 0 — неизвестно

    @property
    def label(self) -> str:
        minutes, seconds = divmod(self.duration, 60)
        length = f"  ·  {minutes}:{seconds:02d}" if self.duration else ""
        return f"{self.title}\n{self.channel}{length}"


def cache_dir() -> Path:
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.CacheLocation
    )
    path = Path(base or Path.home() / ".cache" / "quantis-mobile") / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
                video_id=video_id,
                title=entry.get("title") or video_id,
                channel=entry.get("channel") or entry.get("uploader") or "",
                duration=int(entry.get("duration") or 0),
            )
        )
    return results


def _audio_attempts(outtmpl: str) -> list[dict]:
    """Те же попытки, что у настольного Quantis: сначала быстрый android."""
    common = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "noprogress": True,
        "outtmpl": outtmpl,
        "format": (
            "ba[protocol=https][ext=m4a]/ba[protocol=https]/"
            "bestaudio[protocol=https]/bestaudio"
        ),
    }
    android = {
        **common,
        "extractor_args": {
            "youtube": {
                "player_client": ["android"],
                "skip": ["hls", "dash", "translated_subs"],
                "player_skip": ["webpage", "configs"],
            }
        },
    }
    return [android, common]


def fetch_audio(video_id: str) -> Path:
    """Путь к скачанному звуку; уже скачанный трек не качается снова."""
    import yt_dlp

    folder = cache_dir()
    for existing in folder.glob(f"{video_id}.*"):
        if existing.suffix not in (".part", ".ytdl"):
            return existing
    outtmpl = str(folder / "%(id)s.%(ext)s")
    url = f"https://www.youtube.com/watch?v={video_id}"
    error: Exception | None = None
    for opts in _audio_attempts(outtmpl):
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info))
            if path.exists():
                return path
        except Exception as exc:  # следующая попытка
            error = exc
    raise RuntimeError(f"Не удалось скачать трек: {error}")


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    """Функция в пуле потоков: сеть и yt-dlp не должны держать интерфейс."""

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
QListWidget { background: transparent; border: none; }
QListWidget::item { padding: 12px 6px; border-bottom: 1px solid #1f2230; }
QListWidget::item:selected { background: #222638; color: #ffffff; }
QLabel#status { color: #9aa0b4; font-size: 14px; }
QLabel#now { font-weight: 700; }
QSlider::groove:horizontal { height: 6px; background: #2c3040; border-radius: 3px; }
QSlider::sub-page:horizontal { background: #6c5ce7; border-radius: 3px; }
QSlider::handle:horizontal {
    background: #ffffff; width: 22px; margin: -8px 0; border-radius: 11px;
}
"""


class MobileWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Quantis")
        self._pool = QThreadPool.globalInstance()
        self._jobs: set[Job] = set()  # держим ссылки, пока задачи идут
        self._results: list[Result] = []
        self._current = -1
        self._seeking = False

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

        self._status = QLabel("Найди трек на YouTube")
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
        self._sync_play_button()

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
        self._status.setText(text)

    # --- поиск ------------------------------------------------------------

    def _search(self) -> None:
        query = self._query.text().strip()
        if not query:
            return
        self._search_btn.setEnabled(False)
        self._set_status("Ищем…")
        self._run(search_youtube, (query,), self._on_results, self._on_search_failed)

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
        self._now.setText(f"{result.title}\n{result.channel}")
        self._player.stop()
        self._set_status("Загружаем трек…")
        self._run(
            fetch_audio,
            (result.video_id,),
            lambda path, r=row: self._on_fetched(r, path),
            lambda text: self._set_status(text),
        )

    def _on_fetched(self, row: int, path: Path) -> None:
        if row != self._current:
            return  # пока качали, выбрали другой трек
        self._set_status("")
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

    def _toggle(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        elif self._player.source().isEmpty():
            self._play_at(max(0, self._current))
        else:
            self._player.play()

    def _sync_play_button(self, *_: object) -> None:
        playing = (
            self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        )
        self._play_btn.setText("⏸" if playing else "▶")

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

    def _on_seek_released(self) -> None:
        self._seeking = False
        self._player.setPosition(self._seek.value())


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Quantis")
    app.setOrganizationName("ReallyFun")
    app.setStyleSheet(STYLE)
    _install_ca_bundle()  # после QApplication: нужен путь к кэшу приложения
    window = MobileWindow()
    if os.environ.get("ANDROID_ARGUMENT") or hasattr(sys, "getandroidapilevel"):
        window.showMaximized()
    else:
        window.resize(420, 820)  # проверка на компьютере: размер телефона
        window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
