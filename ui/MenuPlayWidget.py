from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QSlider, QLabel,
    QSizePolicy,
)
from qasync import asyncSlot

from player import Player
from services import AsyncDownloader
from providers import PlaylistManager, PathProvider
from models import Track
import os


# ── style fragments ──

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
    """Spotify-style bottom player bar."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.playlist_manager = PlaylistManager()
        self.player = Player()
        self.downloader = AsyncDownloader()
        self._path_provider = PathProvider()

        self._seeking = False  # True while user drags seek slider

        # ────────── root: three columns ──────────
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 4, 12, 6)
        root.setSpacing(0)

        # ══════ LEFT: cover + text ══════
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

        # ══════ CENTER: buttons + seek ══════
        center = QVBoxLayout()
        center.setSpacing(2)
        center.setContentsMargins(0, 2, 0, 2)

        # buttons row
        btns = QHBoxLayout()
        btns.setSpacing(8)
        btns.setAlignment(Qt.AlignCenter)

        self.btn_repeat = self._btn("assets/icons/repeat_playlist.png", 30)
        self.btn_prev = self._btn("assets/icons/backward.png", 34)
        self.btn_play = self._btn("assets/icons/play.png", 40)
        self.btn_next = self._btn("assets/icons/forward.png", 34)
        self.btn_wave = self._btn("assets/icons/wave.png", 30)

        btns.addWidget(self.btn_repeat)
        btns.addWidget(self.btn_prev)
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_next)
        btns.addWidget(self.btn_wave)

        center.addLayout(btns)

        # seek row: time - slider - time
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

        # ══════ RIGHT: volume ══════
        right = QHBoxLayout()
        right.setSpacing(6)
        right.setContentsMargins(0, 0, 0, 0)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.btn_download = self._btn("assets/icons/download.png", 30)

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

        # ── assemble columns ──
        root.addWidget(left_w, stretch=1)
        root.addWidget(center_w, stretch=2)
        root.addWidget(right_w, stretch=1)

        # ── connections ──
        self.btn_play.clicked.connect(self.pause)
        self.btn_prev.clicked.connect(self.play_previous_track)
        self.btn_next.clicked.connect(self.play_next_track)
        self.btn_download.clicked.connect(self.download_track)

        # ── tick timer ──
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

    # ── update track info ──

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

    # ── tick ──

    def _tick(self) -> None:
        if self._seeking:
            return
        t = self.player.time
        d = self.player.duration
        if d > 0 and t >= 0:
            self._seek.setValue(int(t / d * 1000))
            self._lbl_cur.setText(_fmt(t))
            self._lbl_tot.setText(_fmt(d))

    # ── seek interaction ──

    def _on_seek_press(self) -> None:
        self._seeking = True

    def _on_seek_release(self) -> None:
        d = self.player.duration
        if d > 0:
            ratio = self._seek.value() / 1000
            self.player.time = int(ratio * d)
        self._seeking = False

    # ── slots ──

    @asyncSlot()
    async def pause(self):
        self.player.pause()

    @asyncSlot()
    async def play_previous_track(self):
        track = self.playlist_manager.current_playlist.move_previous_track()
        await self.player.play_track(track)
        await self.set_track(track)

    @asyncSlot()
    async def play_next_track(self):
        track = self.playlist_manager.current_playlist.move_next_track()
        await self.player.play_track(track)
        await self.set_track(track)

    @asyncSlot()
    async def download_track(self):
        await self.downloader.download_track(
            self.playlist_manager.current_playlist.get_current_track(),
        )

    def _on_volume(self) -> None:
        self.player.volume = self._vol.value()

    # ── factory ──

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


# ── helpers ──

def _fmt(ms: int) -> str:
    s = max(0, ms // 1000)
    m, s = divmod(s, 60)
    return f"{m}:{s:02d}"


def _elide(text: str, max_len: int) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"
