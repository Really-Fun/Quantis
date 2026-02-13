"""Страница плейлиста — открывается при клике на карточку плейлиста.

Верх: обложка + название + кол-во треков + кнопки (play all, shuffle).
Ниже: скроллируемый список TrackCard.
"""

from __future__ import annotations

import asyncio
import os
import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QMessageBox, QScrollArea, QFrame, QToolButton, QSizePolicy,
)
from PySide6.QtGui import (
    QPixmap, QColor, QPainter, QLinearGradient, QBrush,
    QPainterPath, QFont, QIcon, QPen,
)
from PySide6.QtCore import Qt, QRectF, Signal, QSize
from qasync import asyncSlot

from models import Track, UserPlaylist
from player import Player
from providers import PlaylistManager, PathProvider
from services import AsyncDownloader
from ui.TrackCard import TrackCard
from utils import remove_track_from_user_playlist
from utils import get_ru_words_for_number

_COVER_SIZE = 160
_COVER_RADIUS = 16
_HEADER_HEIGHT = 220
_PANEL_RADIUS = 16
_ACCENT = QColor(0, 220, 255)
logger = logging.getLogger(__name__)


class PlaylistPage(QWidget):
    """Full playlist view: header + track list."""

    go_back = Signal()  # emitted when user clicks "back"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._player = Player()
        self._pm = PlaylistManager()
        self._path = PathProvider()
        self._dl = AsyncDownloader()
        self._playlist = None
        self._cards: list[TrackCard] = []
        self._playlist_cache_key: tuple[str, ...] | None = None
        self._player.track_changed.connect(self._on_track_changed)

        self.setObjectName("PlaylistPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        # ═══════ HEADER ═══════
        self._header = _PlaylistHeader()
        self._header.back_clicked.connect(self.go_back.emit)
        self._header.play_clicked.connect(self._play_all)
        self._header.shuffle_clicked.connect(self._play_all)
        root.addWidget(self._header)

        root.addSpacing(8)

        # ═══════ TRACK LIST ═══════
        self._list_panel = QFrame()
        self._list_panel.setObjectName("TrackListPanel")
        self._list_panel.setStyleSheet("""
            QFrame#TrackListPanel {
                background: rgba(12, 14, 20, 160);
                border-radius: 16px;
            }
        """)

        list_lay = QVBoxLayout(self._list_panel)
        list_lay.setContentsMargins(12, 10, 12, 10)
        list_lay.setSpacing(0)

        # column header
        col_hdr = QHBoxLayout()
        col_hdr.setContentsMargins(10, 0, 10, 8)

        num_h = QLabel("#")
        num_h.setFixedWidth(22)
        num_h.setAlignment(Qt.AlignCenter)
        num_h.setStyleSheet("color: rgba(255,255,255,50); font-size: 12px; background: transparent;")

        title_h = QLabel("НАЗВАНИЕ")
        title_h.setStyleSheet("color: rgba(255,255,255,50); font-size: 11px; font-weight: 600; background: transparent;")

        source_h = QLabel("ИСТОЧНИК")
        source_h.setAlignment(Qt.AlignRight)
        source_h.setStyleSheet("color: rgba(255,255,255,50); font-size: 11px; font-weight: 600; background: transparent;")

        col_hdr.addWidget(num_h)
        col_hdr.addSpacing(60)  # cover width gap
        col_hdr.addWidget(title_h, stretch=1)
        col_hdr.addWidget(source_h)
        col_hdr.addSpacing(40)

        list_lay.addLayout(col_hdr)

        # divider
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background: rgba(255,255,255,12);")
        list_lay.addWidget(div)
        list_lay.addSpacing(4)

        # scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QWidget#_tlc { background: transparent; }
            QScrollBar:vertical {
                width: 5px; background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,30); border-radius: 2px; min-height: 30px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._track_container = QWidget()
        self._track_container.setObjectName("_tlc")
        self._track_layout = QVBoxLayout(self._track_container)
        self._track_layout.setContentsMargins(0, 0, 0, 0)
        self._track_layout.setSpacing(2)
        self._track_layout.addStretch()

        scroll.setWidget(self._track_container)
        list_lay.addWidget(scroll)

        root.addWidget(self._list_panel, stretch=1)

    # ── public API ──

    @asyncSlot()
    async def load_playlist(self, playlist) -> None:
        """Load and display a playlist."""
        self._playlist = playlist
        self._pm.set_playlist(playlist)
        tracks = list(playlist.tracks.values)
        allow_remove = isinstance(playlist, UserPlaylist)
        new_key = self._build_playlist_cache_key(playlist)

        # Если открыт тот же плейлист без изменений — не пересоздаем карточки.
        if self._playlist_cache_key == new_key and len(self._cards) == len(tracks):
            self._header.set_info(
                name=playlist.name,
                count=len(tracks),
                pixmap=self._try_cover_sync(playlist),
            )
            self._sync_playing_state()
            self._load_covers_bg()
            return

        # clear old cards first
        self._clear_tracks()

        # header — show instantly with whatever cover is on disk
        self._header.set_info(
            name=playlist.name,
            count=len(tracks),
            pixmap=self._try_cover_sync(playlist),
        )

        await self._populate_track_cards(tracks, allow_remove)
        self._playlist_cache_key = new_key

        self._sync_playing_state()

        # covers load lazily in background after the list is visible
        self._load_covers_bg()

    @asyncSlot()
    async def _load_covers_bg(self) -> None:
        """Download missing covers one-by-one without blocking the UI."""
        # header cover (download if missing)
        if self._playlist:
            cover_pm = await self._resolve_cover(self._playlist)
            if cover_pm:
                self._header.set_info(
                    name=self._playlist.name,
                    count=len(self._playlist.tracks.values),
                    pixmap=cover_pm,
                )
        # track card covers
        for card in list(self._cards):
            try:
                await card.load_cover()
            except Exception:
                logger.exception("Не удалось загрузить обложку трека в карточке")

    # ── internal ──

    def _clear_tracks(self) -> None:
        for card in self._cards:
            card.hide()
            card.setParent(None)
            card.deleteLater()
        self._cards.clear()
        # remove all widgets except the stretch
        while self._track_layout.count() > 1:
            item = self._track_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._playlist_cache_key = None

    async def _populate_track_cards(self, tracks: list[Track], allow_remove: bool) -> None:
        """Создает карточки батчами, чтобы не фризить UI на больших плейлистах."""
        batch_size = 30
        for i, track in enumerate(tracks, start=1):
            card = TrackCard(track, index=i, allow_remove_from_playlist=allow_remove)
            card.play_requested.connect(self._on_play)
            card.download_requested.connect(self._on_download)
            card.remove_from_playlist_requested.connect(self._on_remove_from_playlist)
            self._track_layout.insertWidget(self._track_layout.count() - 1, card)
            self._cards.append(card)
            if i % batch_size == 0:
                await asyncio.sleep(0)

    @staticmethod
    def _build_playlist_cache_key(playlist) -> tuple[str, ...]:
        """Возвращает ключ версии плейлиста для кэша рендера."""
        tracks = playlist.tracks.values
        return (playlist.name,) + tuple(f"{t.source}:{t.track_id}" for t in tracks)

    def _try_cover_sync(self, playlist) -> QPixmap | None:
        """Try to load cover from disk instantly (no downloads)."""
        tracks = playlist.tracks.values
        if not tracks:
            return None
        path = self._path.get_cover_path(tracks[0])
        if os.path.isfile(path):
            return QPixmap(path)
        return None

    async def _resolve_cover(self, playlist) -> QPixmap | None:
        if playlist.cover_path and os.path.isfile(playlist.cover_path):
            return QPixmap(playlist.cover_path)
        tracks = playlist.tracks.values
        if not tracks:
            return None
        track = tracks[0]
        path = self._path.get_cover_path(track)
        if not os.path.isfile(path):
            try:
                await self._dl.download_cover(track)
            except Exception:
                logger.exception("Не удалось скачать обложку для трека: %s", track)
        if os.path.isfile(path):
            return QPixmap(path)
        return None

    @asyncSlot(object)
    async def _on_play(self, track) -> None:
        await self._player.play_track(track)

    @asyncSlot(object)
    async def _on_track_changed(self, track) -> None:
        self._sync_playing_state(track)

    @asyncSlot(object)
    async def _on_download(self, track) -> None:
        await self._dl.download_track(track)

    @asyncSlot(object)
    async def _on_remove_from_playlist(self, track) -> None:
        """Удаляет трек из открытого пользовательского плейлиста и сохраняет JSON."""
        if not isinstance(self._playlist, UserPlaylist):
            return
        try:
            removed = remove_track_from_user_playlist(
                self._playlist.name,
                track_id=track.track_id,
            )
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось удалить трек из плейлиста.")
            return

        if not removed:
            QMessageBox.information(self, "Информация", "Трек уже отсутствует в плейлисте.")
            return

        self._playlist.delete_track(track)
        await self.load_playlist(self._playlist)

    @asyncSlot()
    async def _play_all(self) -> None:
        if self._playlist and self._playlist.tracks.values:
            first = self._playlist.tracks.values[0]
            await self._player.play_track(first)

    def _sync_playing_state(self, current_track=None) -> None:
        """Highlight currently playing track if it belongs to this playlist."""
        track = current_track if current_track is not None else self._player.current_track
        for card in self._cards:
            card.set_playing(bool(track is not None and card.track == track))

    # ── paint ──

    def paintEvent(self, event) -> None:
        super().paintEvent(event)


class _PlaylistHeader(QWidget):
    """Playlist cover + info + action buttons."""

    back_clicked = Signal()
    play_clicked = Signal()
    shuffle_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_HEADER_HEIGHT)
        self._cover_pm: QPixmap | None = None
        self._name = ""
        self._count = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(20)

        # back button (top-left inside cover area)
        self._back_btn = QToolButton()
        self._back_btn.setText("←")
        self._back_btn.setFixedSize(36, 36)
        self._back_btn.setCursor(Qt.PointingHandCursor)
        self._back_btn.setStyleSheet("""
            QToolButton {
                color: white; font-size: 18px; font-weight: 700;
                background: rgba(0,0,0,100); border-radius: 18px; border: none;
            }
            QToolButton:hover { background: rgba(0,220,255,60); }
        """)
        self._back_btn.clicked.connect(self.back_clicked.emit)

        # cover placeholder
        self._cover_label = QLabel()
        self._cover_label.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self._cover_label.setAlignment(Qt.AlignCenter)

        # left: back + cover stacked
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(self._back_btn, alignment=Qt.AlignLeft)
        left.addWidget(self._cover_label, alignment=Qt.AlignCenter)
        left.addStretch()
        root.addLayout(left)

        # right: text + buttons
        right = QVBoxLayout()
        right.setSpacing(6)
        right.addStretch()

        tag = QLabel("ПЛЕЙЛИСТ")
        tag.setStyleSheet(
            "color: rgba(255,255,255,60); font-size: 11px; font-weight: 700;"
            " letter-spacing: 2px; background: transparent;"
        )
        right.addWidget(tag)

        self._name_label = QLabel("—")
        self._name_label.setStyleSheet(
            "color: #fff; font-size: 28px; font-weight: 800; background: transparent;"
        )
        self._name_label.setWordWrap(True)
        right.addWidget(self._name_label)

        self._count_label = QLabel("")
        self._count_label.setStyleSheet(
            "color: rgba(255,255,255,80); font-size: 13px; background: transparent;"
        )
        right.addWidget(self._count_label)

        right.addSpacing(10)

        # action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._play_btn = self._action_btn("▶  Играть", accent=True)
        self._play_btn.clicked.connect(self.play_clicked.emit)
        btn_row.addWidget(self._play_btn)

        self._shuffle_btn = self._action_btn("⤮  Перемешать")
        self._shuffle_btn.clicked.connect(self.shuffle_clicked.emit)
        btn_row.addWidget(self._shuffle_btn)

        btn_row.addStretch()
        right.addLayout(btn_row)
        right.addStretch()

        root.addLayout(right, stretch=1)

    def set_info(self, name: str, count: int, pixmap: QPixmap | None) -> None:
        self._name = name
        self._count = count
        self._cover_pm = pixmap
        self._name_label.setText(name)
        self._count_label.setText(get_ru_words_for_number(count))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(0, 0, self.width(), self.height())
        clip = QPainterPath()
        clip.addRoundedRect(rect, _PANEL_RADIUS, _PANEL_RADIUS)
        p.setClipPath(clip)

        # gradient bg
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0.0, QColor(12, 18, 30, 200))
        grad.setColorAt(0.4, QColor(8, 20, 40, 200))
        grad.setColorAt(1.0, QColor(12, 14, 24, 200))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRect(rect)

        # draw cover with rounded corners
        cx, cy = 16, 52  # offset for back btn
        cr = QRectF(cx, cy, _COVER_SIZE, _COVER_SIZE)
        cover_clip = QPainterPath()
        cover_clip.addRoundedRect(cr, _COVER_RADIUS, _COVER_RADIUS)

        p.save()
        p.setClipPath(cover_clip)
        if self._cover_pm and not self._cover_pm.isNull():
            scaled = self._cover_pm.scaled(
                _COVER_SIZE, _COVER_SIZE,
                Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
            )
            p.drawPixmap(int(cx), int(cy), scaled)
        else:
            # placeholder
            pg = QLinearGradient(cr.topLeft(), cr.bottomRight())
            pg.setColorAt(0.0, QColor(30, 40, 60))
            pg.setColorAt(1.0, QColor(20, 30, 50))
            p.setBrush(QBrush(pg))
            p.drawRect(cr)
            p.setPen(QColor(255, 255, 255, 50))
            p.setFont(QFont("Segoe UI", 44))
            p.drawText(cr, Qt.AlignCenter, "♫")
        p.restore()

        # subtle cover shadow/border
        p.setPen(QPen(QColor(0, 0, 0, 40), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(cr, _COVER_RADIUS, _COVER_RADIUS)

        # accent line at bottom
        line_grad = QLinearGradient(0, 0, self.width(), 0)
        line_grad.setColorAt(0.0, QColor(0, 220, 255, 0))
        line_grad.setColorAt(0.3, QColor(0, 220, 255, 30))
        line_grad.setColorAt(0.7, QColor(0, 220, 255, 30))
        line_grad.setColorAt(1.0, QColor(0, 220, 255, 0))
        p.setPen(QPen(QBrush(line_grad), 1.0))
        p.drawLine(16, int(rect.bottom() - 1), int(rect.right() - 16), int(rect.bottom() - 1))

        p.end()
        super().paintEvent(event)

    @staticmethod
    def _action_btn(text: str, accent: bool = False) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        if accent:
            b.setStyleSheet("""
                QToolButton {
                    color: #000; font-size: 13px; font-weight: 700;
                    background: rgb(0,220,255); border: none; border-radius: 16px;
                    padding: 8px 20px;
                }
                QToolButton:hover { background: rgb(0,240,255); }
            """)
        else:
            b.setStyleSheet("""
                QToolButton {
                    color: #fff; font-size: 13px; font-weight: 600;
                    background: rgba(255,255,255,12); border: none; border-radius: 16px;
                    padding: 8px 20px;
                }
                QToolButton:hover { background: rgba(255,255,255,22); }
            """)
        return b
