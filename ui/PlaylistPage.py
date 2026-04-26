"""Страница плейлиста

Открывается при клике на карточку плейлиста.
Верх: обложка, название, кол-во треков, кнопки (играть, перемешать).
Ниже: скроллируемый список карточек треков.
"""

from __future__ import annotations

import asyncio
import logging
import os

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QListView,
)
from qasync import asyncSlot

from models import UserPlaylist
from player import Player
from providers import PlaylistManager, PathProvider
from services import AsyncDownloader
from utils import get_ru_words_for_number, remove_track_from_user_playlist

COVER_SIZE = 160
COVER_RADIUS = 16
HEADER_HEIGHT = 220
PANEL_RADIUS = 16
ACCENT = QColor(0, 220, 255)
logger = logging.getLogger(__name__)


class PlaylistPage(QWidget):
    """Страница плейлиста: шапка с обложкой и список треков."""

    go_back = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.player = Player()
        self.pm = PlaylistManager()
        self.path = PathProvider()
        self.dl = AsyncDownloader()
        self.playlist = None
        self.playlist_cache_key: tuple[str, ...] | None = None
        self.player.track_changed.connect(self.on_track_changed)

        self.setObjectName("PlaylistPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(0)

        # ═══════ HEADER ═══════
        self.header = PlaylistHeader()
        self.header.back_clicked.connect(self.go_back.emit)
        self.header.play_clicked.connect(self.play_all)
        self.header.shuffle_clicked.connect(self.play_all)
        root.addWidget(self.header)

        root.addSpacing(8)

        # ═══════ TRACK LIST ═══════
        self.list_panel = QFrame()
        self.list_panel.setObjectName("TrackListPanel")

        list_lay = QVBoxLayout(self.list_panel)
        list_lay.setContentsMargins(12, 10, 12, 10)
        list_lay.setSpacing(0)

        # column header
        col_hdr = QHBoxLayout()
        col_hdr.setContentsMargins(10, 0, 10, 8)

        num_h = QLabel("#")
        num_h.setObjectName("colHeaderNum")
        num_h.setFixedWidth(22)
        num_h.setAlignment(Qt.AlignCenter)

        title_h = QLabel("НАЗВАНИЕ")
        title_h.setObjectName("colHeaderTitle")

        source_h = QLabel("ИСТОЧНИК")
        source_h.setObjectName("colHeaderSource")
        source_h.setAlignment(Qt.AlignRight)

        col_hdr.addWidget(num_h)
        col_hdr.addSpacing(60)  # cover width gap
        col_hdr.addWidget(title_h, stretch=1)
        col_hdr.addWidget(source_h)
        col_hdr.addSpacing(40)

        list_lay.addLayout(col_hdr)

        # divider
        div = QFrame()
        div.setObjectName("listDivider")
        div.setFixedHeight(1)
        list_lay.addWidget(div)
        list_lay.addSpacing(4)

        # scroll
        self.track_list = QListView()
        self.track_list.setObjectName("trackListView")
        self.track_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.track_list.setFrameShape(QFrame.NoFrame)
        self.track_list.setSelectionMode(QListView.NoSelection)
        self.track_list.setMouseTracking(True)  # Required for hover events in delegate

        from models import TrackListModel
        from ui.delegates.TrackDelegate import TrackDelegate

        self.track_model = TrackListModel()
        self.track_delegate = TrackDelegate(self.track_list)

        self.track_delegate.signals.play_requested.connect(self.on_play)
        self.track_delegate.signals.download_requested.connect(self.on_download)
        self.track_delegate.signals.context_menu_requested.connect(self.on_context_menu)

        self.track_list.setModel(self.track_model)
        self.track_list.setItemDelegate(self.track_delegate)

        list_lay.addWidget(self.track_list)

        root.addWidget(self.list_panel, stretch=1)

    # ── public API ──

    @asyncSlot()
    async def load_playlist(self, playlist) -> None:
        self.playlist = playlist
        self.pm.set_playlist(playlist)
        tracks = list(playlist.tracks.values)
        self._allow_remove = isinstance(playlist, UserPlaylist)
        new_key = self.build_playlist_cache_key(playlist)

        if self.playlist_cache_key == new_key and self.track_model.rowCount() == len(tracks):
            self.header.set_info(
                name=playlist.name,
                count=len(tracks),
                pixmap=self.try_cover_sync(playlist),
            )
            self.sync_playing_state()
            self.load_covers_bg()
            return

        self.header.set_info(
            name=playlist.name,
            count=len(tracks),
            pixmap=self.try_cover_sync(playlist),
        )

        self.track_model.set_tracks(tracks)
        self.playlist_cache_key = new_key

        self.sync_playing_state()
        self.load_covers_bg()

    @asyncSlot()
    async def load_covers_bg(self) -> None:
        if self.playlist:
            cover_pm = await self.resolve_cover(self.playlist)
            if cover_pm:
                self.header.set_info(
                    name=self.playlist.name,
                    count=len(self.playlist.tracks.values),
                    pixmap=cover_pm,
                )

        tracks = self.track_model._tracks
        for track in tracks:
            path = self.path.get_cover_path(track)
            if not os.path.isfile(path):
                try:
                    await self.dl.download_cover(track)
                    idx = tracks.index(track)
                    self.track_model.dataChanged.emit(
                        self.track_model.index(idx), self.track_model.index(idx)
                    )
                except Exception:
                    logger.exception("Не удалось загрузить обложку трека")
            await asyncio.sleep(0)

    # ── internal ──

    @staticmethod
    def build_playlist_cache_key(playlist) -> tuple[str, ...]:
        tracks = playlist.tracks.values
        return (playlist.name,) + tuple(f"{t.source}:{t.track_id}" for t in tracks)

    def try_cover_sync(self, playlist) -> QPixmap | None:
        tracks = playlist.tracks.values
        if not tracks:
            return None
        path = self.path.get_cover_path(tracks[0])
        if os.path.isfile(path):
            return QPixmap(path)
        return None

    async def resolve_cover(self, playlist) -> QPixmap | None:
        if playlist.cover_path and os.path.isfile(playlist.cover_path):
            return QPixmap(playlist.cover_path)
        tracks = playlist.tracks.values
        if not tracks:
            return None
        track = tracks[0]
        path = self.path.get_cover_path(track)
        if not os.path.isfile(path):
            try:
                await self.dl.download_cover(track)
            except Exception:
                logger.exception("Не удалось скачать обложку для трека: %s", track)
        if os.path.isfile(path):
            return QPixmap(path)
        return None

    @asyncSlot(object)
    async def on_play(self, track) -> None:
        if self.playlist:
            try:
                idx = self.playlist.tracks.values.index(track)
                self.playlist.set_current_track(idx)
            except (ValueError, IndexError):
                pass
        await self.player.play_track(track)

    @asyncSlot(object)
    async def on_track_changed(self, track) -> None:
        self.sync_playing_state(track)

    @asyncSlot(object)
    async def on_download(self, track) -> None:
        await self.dl.download_track(track)

    @asyncSlot(object)
    async def on_remove_from_playlist(self, track) -> None:
        if not isinstance(self.playlist, UserPlaylist):
            return
        try:
            removed = remove_track_from_user_playlist(
                self.playlist.name,
                track_id=track.track_id,
            )
        except Exception:
            QMessageBox.warning(self, "Ошибка", "Не удалось удалить трек из плейлиста.")
            return

        if not removed:
            QMessageBox.information(
                self, "Информация", "Трек уже отсутствует в плейлисте."
            )
            return

        self.playlist.delete_track(track)
        await self.load_playlist(self.playlist)

    @asyncSlot()
    async def play_all(self) -> None:
        if self.playlist and self.playlist.tracks.values:
            self.playlist.set_current_track(0)
            first = self.playlist.tracks.values[0]
            await self.player.play_track(first)

    def sync_playing_state(self, current_track=None) -> None:
        track = (
            current_track if current_track is not None else self.player.current_track
        )
        self.track_model.set_playing_track(track)

    @asyncSlot(object, object)
    async def on_context_menu(self, track, global_pos):
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        play_action = menu.addAction("Играть")
        add_action = menu.addAction("Добавить в плейлист")
        remove_action = None
        if getattr(self, "_allow_remove", False):
            remove_action = menu.addAction("Удалить из плейлиста")
        download_action = menu.addAction("Скачать")

        chosen = menu.exec(global_pos)
        if chosen == play_action:
            await self.on_play(track)
        elif chosen == add_action:
            pass
        elif remove_action is not None and chosen == remove_action:
            await self.on_remove_from_playlist(track)
        elif chosen == download_action:
            await self.on_download(track)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)


class PlaylistHeader(QWidget):
    """Шапка страницы: обложка, название, кол-во треков, кнопки действий."""

    back_clicked = Signal()
    play_clicked = Signal()
    shuffle_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PlaylistHeader")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(HEADER_HEIGHT)
        self.cover_pm: QPixmap | None = None
        self.name = ""
        self.count = 0

        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(20)

        # back button
        self.back_btn = QToolButton()
        self.back_btn.setObjectName("backButton")
        self.back_btn.setText("←")
        self.back_btn.setFixedSize(36, 36)
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_clicked.emit)

        # cover placeholder
        self.cover_label = QLabel()
        self.cover_label.setFixedSize(COVER_SIZE, COVER_SIZE)
        self.cover_label.setAlignment(Qt.AlignCenter)

        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(self.back_btn, alignment=Qt.AlignLeft)
        left.addWidget(self.cover_label, alignment=Qt.AlignCenter)
        left.addStretch()
        root.addLayout(left)

        right = QVBoxLayout()
        right.setSpacing(6)
        right.addStretch()

        tag = QLabel("ПЛЕЙЛИСТ")
        tag.setObjectName("playlistTag")
        right.addWidget(tag)

        self.name_label = QLabel("—")
        self.name_label.setObjectName("playlistName")
        self.name_label.setWordWrap(True)
        right.addWidget(self.name_label)

        self.count_label = QLabel("")
        self.count_label.setObjectName("playlistCount")
        right.addWidget(self.count_label)

        right.addSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.play_btn = self.action_btn("▶  Играть", accent=True)
        self.play_btn.clicked.connect(self.play_clicked.emit)
        btn_row.addWidget(self.play_btn)

        self.shuffle_btn = self.action_btn("⤮  Перемешать")
        self.shuffle_btn.clicked.connect(self.shuffle_clicked.emit)
        btn_row.addWidget(self.shuffle_btn)

        btn_row.addStretch()
        right.addLayout(btn_row)
        right.addStretch()

        root.addLayout(right, stretch=1)

    def set_info(self, name: str, count: int, pixmap: QPixmap | None) -> None:
        self.name = name
        self.count = count
        self.cover_pm = pixmap
        self.name_label.setText(name)
        self.count_label.setText(get_ru_words_for_number(count))
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(0, 0, self.width(), self.height())
        clip = QPainterPath()
        clip.addRoundedRect(rect, PANEL_RADIUS, PANEL_RADIUS)
        p.setClipPath(clip)



        # draw cover with rounded corners
        cx, cy = 16, 52  # offset for back btn
        cr = QRectF(cx, cy, COVER_SIZE, COVER_SIZE)
        cover_clip = QPainterPath()
        cover_clip.addRoundedRect(cr, COVER_RADIUS, COVER_RADIUS)

        p.save()
        p.setClipPath(cover_clip)
        if self.cover_pm and not self.cover_pm.isNull():
            scaled = self.cover_pm.scaled(
                COVER_SIZE,
                COVER_SIZE,
                Qt.KeepAspectRatioByExpanding,
                Qt.SmoothTransformation,
            )
            p.drawPixmap(int(cx), int(cy), scaled)
        else:
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
        p.drawRoundedRect(cr, COVER_RADIUS, COVER_RADIUS)



        p.end()
        super().paintEvent(event)

    @staticmethod
    def action_btn(text: str, accent: bool = False) -> QToolButton:
        b = QToolButton()
        b.setObjectName("actionButton")
        b.setProperty("accent", "true" if accent else "false")
        b.setText(text)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolButtonStyle(Qt.ToolButtonTextOnly)
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        return b