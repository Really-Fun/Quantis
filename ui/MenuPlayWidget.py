"""Нижняя панель плеера.

Управление воспроизведением, перемотка, громкость, следующая/предыдущая.
"""

import asyncio
import os

from PySide6.QtCore import QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QSlider, QToolButton, QVBoxLayout, QWidget
from qasync import asyncSlot
from PySide6.QtGui import QKeySequence, QShortcut

from models import Track
from player import Player
from providers import PathProvider, PlaylistManager
from services import AsyncDownloader
from utils import asset_path

_BG_COLOR = QColor(0, 0, 0, 200)
_BG_RADIUS = 18


# ── фрагменты стилей ──

_SLIDER_QSS = """
    QSlider::groove:horizontal {
        height: 4px;
        background: rgba(255,255,255,30);
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        width: 12px; height: 12px; margin: -4px 0;
        background: #fff;
        border-radius: 6px;
    }
    QSlider::handle:horizontal:hover {
        background: rgb(0,220,255);
    }
    QSlider::sub-page:horizontal {
        background: #fff;
        border-radius: 2px;
    }
    QSlider::sub-page:horizontal:hover {
        background: rgb(0,220,255);
        border-radius: 2px;
    }
"""

_VOL_QSS = """
    QSlider::groove:horizontal {
        height: 4px;
        background: rgba(255,255,255,30);
        border-radius: 2px;
    }
    QSlider::handle:horizontal {
        width: 10px; height: 10px; margin: -3px 0;
        background: #fff;
        border-radius: 5px;
    }
    QSlider::sub-page:horizontal {
        background: rgba(255,255,255,120);
        border-radius: 2px;
    }
"""

_TIME_QSS = "color: rgba(255,255,255,90); font-size: 11px; background: transparent;"
_TITLE_QSS = "color: #fff; font-size: 13px; font-weight: 500; background: transparent;"
_ARTIST_QSS = "color: rgba(255,255,255,110); font-size: 11px; background: transparent;"


class PlayMenu(QWidget):
    """Панель управления воспроизведением."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.playlist_manager = PlaylistManager()
        self.player = Player()
        self.downloader = AsyncDownloader()
        self._path_provider = PathProvider()

        self._seeking = False  # True, пока пользователь двигает ползунок перемотки
        self._repeat_mode = "off"  # "off" | "one" | "all"

        # ────────── корневой layout: 3 колонки ──────────
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 4, 12, 6)
        root.setSpacing(0)

        # ══════ СЛЕВА: обложка + текст ══════
        left = QHBoxLayout()
        left.setSpacing(10)
        left.setContentsMargins(0, 0, 0, 0)

        self._cover = QLabel()
        self._cover.setFixedSize(48, 48)
        self._cover.setAlignment(Qt.AlignCenter)
        self._cover.setStyleSheet("border-radius: 6px; background: rgba(255,255,255,8);")

        txt = QVBoxLayout()
        txt.setSpacing(2)
        txt.setContentsMargins(0, 4, 0, 4)

        self._title = QLabel("—")
        self._title.setStyleSheet(_TITLE_QSS)
        self._title.setMaximumWidth(180)
        self._title.setWordWrap(False)

        self._artist = QLabel("")
        self._artist.setStyleSheet(_ARTIST_QSS)
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

        # ряд кнопок
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.setAlignment(Qt.AlignCenter)

        self.btn_repeat = self._btn(asset_path("assets/icons/repeat_playlist.png"), 30)
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

        # ряд перемотки: время - ползунок - время
        seek_row = QHBoxLayout()
        seek_row.setSpacing(6)
        seek_row.setContentsMargins(0, 0, 0, 0)

        self._lbl_cur = QLabel("0:00")
        self._lbl_cur.setStyleSheet(_TIME_QSS)
        self._lbl_cur.setFixedWidth(36)
        self._lbl_cur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self._seek = QSlider(Qt.Horizontal)
        self._seek.setRange(0, 1000)
        self._seek.setValue(0)
        self._seek.setCursor(Qt.PointingHandCursor)
        self._seek.setStyleSheet(_SLIDER_QSS)
        self._seek.sliderPressed.connect(self._on_seek_press)
        self._seek.sliderReleased.connect(self._on_seek_release)
        self._seek.setMinimumWidth(200)

        self._lbl_tot = QLabel("0:00")
        self._lbl_tot.setStyleSheet(_TIME_QSS)
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
        vol_icon.setStyleSheet("font-size: 14px; background: transparent;")

        self._vol = QSlider(Qt.Horizontal)
        self._vol.setRange(0, 100)
        self._vol.setValue(70)
        self._vol.setFixedWidth(90)
        self._vol.setStyleSheet(_VOL_QSS)
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

        # ── реакция на завершение трека ──
        self.player.track_finished.connect(self._on_track_finished)

        # ── таймер обновления ──
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

        # ── реакция на смену трека ──
        self.player.track_changed.connect(self._on_track_changed)

        self._update_repeat_button_style()

    # ── темный овальный фон ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(_BG_COLOR)
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), _BG_RADIUS, _BG_RADIUS)
        p.end()
        super().paintEvent(event)

    # ── трек сменился из любого места приложения ──

    @asyncSlot(object)
    async def _on_track_changed(self, track) -> None:
        await self.set_track(track)
        self.btn_play.setIcon(QIcon(asset_path("assets/icons/pause.png")))

    # ── обновление информации о треке ──

    async def set_track(self, track: Track) -> None:
        self._title.setText(_elide(track.title, 22))
        self._artist.setText(_elide(track.author, 24))
        path = self._path_provider.get_cover_path(track)
        if not os.path.exists(path):
            await self.downloader.download_cover(track)
        if os.path.exists(path):
            pm = QPixmap(path).scaled(
                48, 48, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
            )
            self._cover.setPixmap(pm)

    # ── тик таймера ──

    def _tick(self) -> None:
        if self._seeking:
            return
        t = self.player.time
        d = self.player.duration
        if d > 0 and t >= 0:
            self._seek.setValue(int(t / d * 1000))
            self._lbl_cur.setText(_fmt(t))
            self._lbl_tot.setText(_fmt(d))

    # ── взаимодействие с перемоткой ──

    def _on_seek_press(self) -> None:
        self._seeking = True

    def _on_seek_release(self) -> None:
        d = self.player.duration
        if d > 0:
            ratio = self._seek.value() / 1000
            self.player.time = int(ratio * d)
        self._seeking = False

    # ── слоты ──

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
        """Обработка запроса предыдущего трека (MPRIS, кнопки на наушниках)."""
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

    def _on_next_requested(self):
        """Обработка запроса следующего трека (MPRIS, кнопки на наушниках)."""
        try:
            self.play_next_track()
        except RuntimeError:
            pass

    def _cycle_repeat_mode(self) -> None:
        """Цикл: выкл → один трек → весь плейлист → выкл."""
        modes = ("off", "one", "all")
        idx = (modes.index(self._repeat_mode) + 1) % len(modes)
        self._repeat_mode = modes[idx]
        tips = {"off": "Повтор: выкл", "one": "Повтор: один трек", "all": "Повтор: плейлист"}
        self.btn_repeat.setToolTip(tips[self._repeat_mode])
        self._update_repeat_button_style()

    def _update_repeat_button_style(self) -> None:
        """Обновляет визуальное состояние кнопки повтора."""
        size = 30
        if self._repeat_mode == "off":
            style = """
                QToolButton { border-radius: 15px; background: transparent; border: none; }
                QToolButton:hover { background: rgba(255,255,255,15); }
            """
        else:
            style = f"""
                QToolButton {{
                    border-radius: 15px;
                    background: rgba(0,220,255,40);
                    border: none;
                }}
                QToolButton:hover {{
                    background: rgba(0,220,255,60);
                }}
            """
        self.btn_repeat.setStyleSheet(style)

    @asyncSlot()
    async def _on_track_finished(self) -> None:
        """По завершении трека: повтор одного или переход к следующему."""
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
            self.playlist_manager.current_playlist.get_current_track(),
        )

    def _on_volume(self) -> None:
        self.player.volume = self._vol.value()

    def _on_volume_up(self) -> None:
        self.player.volume = min(100, self.player.volume + 10)
        self._vol.setValue(self.player.volume)

    def _on_volume_down(self) -> None:
        self.player.volume = max(0, self.player.volume - 10)
        self._vol.setValue(self.player.volume)

    # ── фабрика кнопок ──

    @staticmethod
    def _btn(icon_path: str, size: int = 50) -> QToolButton:
        b = QToolButton()
        b.setIcon(QIcon(icon_path))
        b.setIconSize(QSize(int(size * 0.6), int(size * 0.6)))
        b.setFixedSize(size, size)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet(f"""
            QToolButton {{
                border-radius: {size // 2}px;
                background: transparent;
                border: none;
            }}
            QToolButton:hover {{
                background: rgba(255,255,255,15);
            }}
        """)
        return b


# ── вспомогательные функции ──

def _fmt(ms: int) -> str:
    s = max(0, ms // 1000)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def _elide(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"
