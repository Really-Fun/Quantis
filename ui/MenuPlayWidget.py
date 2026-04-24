"""Нижняя панель плеера.

Управление воспроизведением, перемотка, громкость, следующая/предыдущая.
"""

import os

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qasync import asyncSlot

from models import Track
from player import Player
from providers import PathProvider, PlaylistManager
from services import AsyncDownloader, AsyncRecomendation
from utils import asset_path

_BG_COLOR = QColor(0, 0, 0, 200)
_BG_RADIUS = 18


class PlayMenu(QWidget):
    """Панель управления воспроизведением."""

    playlist_generated = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Применяем стили ко всему виджету панели
        with open("styles/play_menu.qss") as file:
            self.setStyleSheet(file.read())

        self.playlist_manager = PlaylistManager()
        self.player = Player()
        self.downloader = AsyncDownloader()
        self._path_provider = PathProvider()

        self._seeking = False
        self._repeat_mode = "off"

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 4, 12, 6)
        root.setSpacing(0)

        # ══════ СЛЕВА: обложка + текст ══════
        left = QHBoxLayout()
        left.setSpacing(10)
        left.setContentsMargins(0, 0, 0, 0)

        self._cover = QLabel()
        self._cover.setObjectName("coverLabel")
        self._cover.setFixedSize(48, 48)
        self._cover.setAlignment(Qt.AlignCenter)

        txt = QVBoxLayout()
        txt.setSpacing(2)
        txt.setContentsMargins(0, 4, 0, 4)

        self._title = QLabel("—")
        self._title.setObjectName("trackTitle")
        self._title.setMaximumWidth(180)
        self._title.setWordWrap(False)

        self._artist = QLabel("")
        self._artist.setObjectName("trackArtist")
        self._artist.setMaximumWidth(180)
        self._artist.setWordWrap(False)

        txt.addStretch()
        txt.addWidget(self._title)
        txt.addWidget(self._artist)
        txt.addStretch()

        left.addWidget(self._cover)
        left.addLayout(txt)

        left_w = QWidget()
        left_w.setLayout(left)
        left_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # ══════ ЦЕНТР: кнопки + перемотка ══════
        center = QVBoxLayout()
        center.setSpacing(2)
        center.setContentsMargins(0, 2, 0, 2)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.setAlignment(Qt.AlignCenter)

        self.btn_repeat = self._btn(asset_path("assets/icons/repeat_playlist.png"), 30)
        self.btn_repeat.setObjectName("repeatButton")
        self.btn_repeat.setProperty("state", "off")
        self.btn_repeat.setToolTip("Повтор: выкл")
        
        self.btn_prev = self._btn(asset_path("assets/icons/backward.png"), 34)
        self.btn_play = self._btn(asset_path("assets/icons/play.png"), 40)
        self.btn_next = self._btn(asset_path("assets/icons/forward.png"), 34)
        self.btn_wave = self._btn(asset_path("assets/icons/wave.png"), 30)

        btns.addWidget(self.btn_repeat)
        btns.addWidget(self.btn_prev)
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_next)
        btns.addWidget(self.btn_wave)

        center.addLayout(btns)

        seek_row = QHBoxLayout()
        seek_row.setSpacing(6)
        seek_row.setContentsMargins(0, 0, 0, 0)

        self._lbl_cur = QLabel("0:00")
        self._lbl_cur.setObjectName("timeLabel")
        self._lbl_cur.setFixedWidth(36)
        self._lbl_cur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._seek = QSlider(Qt.Horizontal)
        self._seek.setObjectName("seekSlider")
        self._seek.setRange(0, 1000)
        self._seek.setValue(0)
        self._seek.setCursor(Qt.PointingHandCursor)
        self._seek.sliderPressed.connect(self._on_seek_press)
        self._seek.sliderReleased.connect(self._on_seek_release)
        self._seek.setMinimumWidth(200)

        self._lbl_tot = QLabel("0:00")
        self._lbl_tot.setObjectName("timeLabel")
        self._lbl_tot.setFixedWidth(36)
        self._lbl_tot.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        seek_row.addWidget(self._lbl_cur)
        seek_row.addWidget(self._seek, stretch=1)
        seek_row.addWidget(self._lbl_tot)

        center.addLayout(seek_row)

        center_w = QWidget()
        center_w.setLayout(center)
        center_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # ══════ СПРАВА: громкость ══════
        right = QHBoxLayout()
        right.setSpacing(6)
        right.setContentsMargins(0, 0, 0, 0)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.btn_download = self._btn(asset_path("assets/icons/download.png"), 30)

        vol_icon = QLabel("🔊")
        vol_icon.setObjectName("volIcon")

        self._vol = QSlider(Qt.Horizontal)
        self._vol.setObjectName("volSlider")
        self._vol.setRange(0, 100)
        self._vol.setValue(70)
        self._vol.setFixedWidth(90)
        self._vol.valueChanged.connect(self._on_volume)

        right.addWidget(self.btn_download)
        right.addSpacing(8)
        right.addWidget(vol_icon)
        right.addWidget(self._vol)

        right_w = QWidget()
        right_w.setLayout(right)
        right_w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        # ── собираем колонки ──
        root.addWidget(left_w, stretch=1)
        root.addWidget(center_w, stretch=2)
        root.addWidget(right_w, stretch=1)

        # ── сигналы ──
        self.btn_play.clicked.connect(self.toggle_playback)
        self.btn_repeat.clicked.connect(self._cycle_repeat_mode)
        self.btn_prev.clicked.connect(self.play_previous_track)
        self.btn_next.clicked.connect(self.play_next_track)
        self.player.next_requested.connect(self._on_next_requested)
        self.player.previous_requested.connect(self._on_previous_requested)
        self.btn_download.clicked.connect(self.download_track)
        self.btn_wave.clicked.connect(self.generate_playlist)

        # ── реакция на нажатие клавиш ──
        self.btn_play.setShortcut(QKeySequence("Space"))
        self.btn_prev.setShortcut(QKeySequence("Left"))
        self.btn_next.setShortcut(QKeySequence("Right"))
        self.btn_repeat.setShortcut(QKeySequence("R"))
        self.btn_download.setShortcut(QKeySequence("D"))
        self.btn_wave.setShortcut(QKeySequence("W"))

        key_shortcut_for_volume_up = QShortcut(QKeySequence("Up"), self)
        key_shortcut_for_volume_up.activated.connect(self._on_volume_up)
        key_shortcut_for_volume_down = QShortcut(QKeySequence("Down"), self)
        key_shortcut_for_volume_down.activated.connect(self._on_volume_down)

        self.player.track_finished.connect(self._on_track_finished)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

        self.player.track_changed.connect(self._on_track_changed)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(_BG_COLOR)
        p.drawRoundedRect(
            QRectF(0, 0, self.width(), self.height()), _BG_RADIUS, _BG_RADIUS
        )
        p.end()
        super().paintEvent(event)

    @asyncSlot(object)
    async def _on_track_changed(self, track) -> None:
        await self.set_track(track)
        self.btn_play.setIcon(QIcon(asset_path("assets/icons/pause.png")))

    async def set_track(self, track: Track) -> None:
        self._title.setText(_elide(track.title, 22))
        self._artist.setText(_elide(track.author, 24))
        path = self._path_provider.get_cover_path(track)
        if not os.path.exists(path):
            await self.downloader.download_cover(track)
        if os.path.exists(path):
            pm = QPixmap(path).scaled(
                48,
                48,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            self._cover.setPixmap(pm)

    def _tick(self) -> None:
        if self._seeking:
            return
        t = self.player.time
        d = self.player.duration
        if d > 0 and t >= 0:
            self._seek.setValue(int(t / d * 1000))
            self._lbl_cur.setText(_fmt(t))
            self._lbl_tot.setText(_fmt(d))

    def _on_seek_press(self) -> None:
        self._seeking = True

    def _on_seek_release(self) -> None:
        d = self.player.duration
        if d > 0:
            ratio = self._seek.value() / 1000
            self.player.time = int(ratio * d)
        self._seeking = False

    @asyncSlot()
    async def toggle_playback(self):
        if self.player.is_playing():
            self.player.pause()
            self.btn_play.setIcon(QIcon(asset_path("assets/icons/play.png")))
            return
        self.player.resume()
        self.btn_play.setIcon(QIcon(asset_path("assets/icons/pause.png")))

    @asyncSlot()
    async def play_previous_track(self):
        track = self.playlist_manager.current_playlist.move_previous_track()
        await self.player.play_track(track)
        await self.set_track(track)
        self.btn_play.setIcon(QIcon(asset_path("assets/icons/pause.png")))

    def _on_previous_requested(self):
        try:
            self.play_previous_track()
        except RuntimeError:
            pass

    @asyncSlot()
    async def play_next_track(self):
        track = self.playlist_manager.current_playlist.move_next_track()
        await self.player.play_track(track)
        await self.set_track(track)
        self.btn_play.setIcon(QIcon(asset_path("assets/icons/pause.png")))

    @asyncSlot()
    async def generate_playlist(self):
        recomendation_service = AsyncRecomendation()
        current_track = self.player.current_track
        if current_track:
            playlist = await recomendation_service.generate_radio_from_track(
                current_track
            )
            self.playlist_generated.emit(playlist)

    def _on_next_requested(self):
        try:
            self.play_next_track()
        except RuntimeError:
            pass

    def _cycle_repeat_mode(self) -> None:
        modes = ("off", "one", "all")
        idx = (modes.index(self._repeat_mode) + 1) % len(modes)
        self._repeat_mode = modes[idx]
        tips = {
            "off": "Повтор: выкл",
            "one": "Повтор: один трек",
            "all": "Повтор: плейлист",
        }
        self.btn_repeat.setToolTip(tips[self._repeat_mode])
        self._update_repeat_button_style()

    def _update_repeat_button_style(self) -> None:
        """Обновляет визуальное состояние кнопки повтора через Property."""
        if self._repeat_mode == "off":
            self.btn_repeat.setProperty("state", "off")
        else:
            self.btn_repeat.setProperty("state", "active")
        
        # Заставляем Qt пересчитать стили виджета с учетом нового свойства
        self.btn_repeat.style().unpolish(self.btn_repeat)
        self.btn_repeat.style().polish(self.btn_repeat)

    @asyncSlot()
    async def _on_track_finished(self) -> None:
        if self._repeat_mode == "one":
            current = self.playlist_manager.current_playlist.get_current_track()
            if current is not None:
                await self.player.play_track(current)
                await self.set_track(current)
                self.btn_play.setIcon(QIcon(asset_path("assets/icons/pause.png")))
                return
        await self.play_next_track()

    @asyncSlot()
    async def download_track(self):
        await self.downloader.download_track(
            self.player.current_track,
        )

    def _on_volume(self) -> None:
        self.player.volume = self._vol.value()

    def _on_volume_up(self) -> None:
        self.player.volume = min(100, self.player.volume + 10)
        self._vol.setValue(self.player.volume)

    def _on_volume_down(self) -> None:
        self.player.volume = max(0, self.player.volume - 10)
        self._vol.setValue(self.player.volume)

    @staticmethod
    def _btn(icon_path: str, size: int = 50) -> QToolButton:
        b = QToolButton()
        b.setObjectName("controlButton")
        b.setIcon(QIcon(icon_path))
        b.setIconSize(QSize(int(size * 0.6), int(size * 0.6)))
        b.setFixedSize(size, size)
        b.setCursor(Qt.PointingHandCursor)
        
        # Динамически задаем радиус скругления через инлайн-стиль, 
        # так как он зависит от аргумента `size`, но базовый стиль берется из QSS.
        b.setStyleSheet(f"border-radius: {size // 2}px;")
        return b


def _fmt(ms: int) -> str:
    s = max(0, ms // 1000)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"

def _elide(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"