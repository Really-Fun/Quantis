from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.models.playlist import RecommendationPlaylist, WavePlaylist
from quantis.ui.async_ui import schedule
from quantis.ui.playlist_actions import show_add_to_playlist_menu
from quantis.ui.viewmodels.playlist_vm import PlaylistViewModel
from quantis.ui.views.widgets.cover_art import playlist_cover_path
from quantis.ui.views.widgets.playlist_card import GradientCover
from quantis.ui.views.widgets.playlist_track_delegate import PlaylistTrackDelegate


class PlaylistTrackTable(QTableView):
    """Таблица треков: QTableView + ленивая подгрузка, без QListView."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("trackListView")
        self.verticalHeader().hide()
        self.horizontalHeader().hide()
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setMinimumSectionSize(240)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setDefaultSectionSize(PlaylistTrackDelegate.ROW_HEIGHT)
        self.setShowGrid(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAlternatingRowColors(False)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_column_width()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_column_width()

    def _sync_column_width(self) -> None:
        width = max(self.viewport().width(), 240)
        if self.columnWidth(0) != width:
            self.setColumnWidth(0, width)


class PlaylistPage(QWidget):
    back_requested = Signal()

    def __init__(
        self,
        view_model: PlaylistViewModel,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._bridge = bridge
        self.setObjectName("playlistPage")

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(0)

        panel = QFrame()
        panel.setObjectName("TrackListPanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(24, 20, 24, 18)
        panel_layout.setSpacing(0)

        panel_layout.addLayout(self._build_header())
        panel_layout.addSpacing(16)
        panel_layout.addLayout(self._build_actions())
        panel_layout.addSpacing(14)

        divider = QFrame()
        divider.setObjectName("listDivider")
        divider.setFixedHeight(1)
        panel_layout.addWidget(divider)
        panel_layout.addSpacing(10)

        panel_layout.addLayout(self._build_column_headers())
        panel_layout.addWidget(self._build_track_table(), stretch=1)

        root.addWidget(panel, stretch=1)

        self._vm.playlist_changed.connect(self._sync_header)
        self._vm.covers_ready.connect(self._on_covers_ready)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(18)

        back = QPushButton("←")
        back.setObjectName("backButton")
        back.setFixedSize(40, 40)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self.back_requested.emit)
        row.addWidget(back, alignment=Qt.AlignmentFlag.AlignTop)

        cover_frame = QFrame()
        cover_frame.setObjectName("playlistCoverFrame")
        cover_frame.setFixedSize(132, 132)
        cover_layout = QVBoxLayout(cover_frame)
        cover_layout.setContentsMargins(6, 6, 6, 6)
        self._cover = GradientCover("", size=120)
        cover_layout.addWidget(self._cover, alignment=Qt.AlignmentFlag.AlignCenter)
        row.addWidget(cover_frame, alignment=Qt.AlignmentFlag.AlignTop)

        meta = QVBoxLayout()
        meta.setSpacing(6)
        meta.setContentsMargins(0, 8, 0, 0)
        self._tag = QLabel("ПЛЕЙЛИСТ")
        self._tag.setObjectName("playlistTag")
        meta.addWidget(self._tag)
        self._name = QLabel("—")
        self._name.setObjectName("playlistName")
        self._name.setWordWrap(True)
        meta.addWidget(self._name)
        self._count = QLabel("")
        self._count.setObjectName("playlistCount")
        meta.addWidget(self._count)
        meta.addStretch()
        row.addLayout(meta, stretch=1)

        return row

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)

        play = QPushButton("▶  Слушать")
        play.setObjectName("actionButton")
        play.setProperty("accent", True)
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setMinimumHeight(40)
        play.clicked.connect(self._on_play_all)
        row.addWidget(play)

        shuffle = QPushButton("⇄  Перемешать")
        shuffle.setObjectName("actionButton")
        shuffle.setProperty("accent", False)
        shuffle.setCursor(Qt.CursorShape.PointingHandCursor)
        shuffle.setMinimumHeight(40)
        shuffle.clicked.connect(self._on_shuffle)
        row.addWidget(shuffle)
        row.addStretch()
        return row

    def _build_column_headers(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(8, 0, 8, 4)
        row.setSpacing(12)

        num = QLabel("#")
        num.setObjectName("colHeaderNum")
        num.setFixedWidth(36)
        num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(num)

        title = QLabel("НАЗВАНИЕ")
        title.setObjectName("colHeaderTitle")
        row.addWidget(title, stretch=1)

        source = QLabel("ИСТОЧНИК")
        source.setObjectName("colHeaderSource")
        source.setFixedWidth(52)
        source.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(source)
        return row

    def _build_track_table(self) -> PlaylistTrackTable:
        table = PlaylistTrackTable(self)
        table.setModel(self._vm.model)
        table.setItemDelegate(PlaylistTrackDelegate(table))
        table.doubleClicked.connect(self._on_play_row)
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._on_context_menu)
        delete = QShortcut(QKeySequence.StandardKey.Delete, table)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete.activated.connect(self._on_delete_selected)
        self._table = table
        return table

    def _sync_header(self) -> None:
        playlist = self._vm.playlist
        if playlist is None:
            self._name.setText("—")
            self._count.setText("")
            return
        self._name.setText(playlist.name)
        if isinstance(playlist, WavePlaylist):
            self._tag.setText("ВОЛНА")
        elif isinstance(playlist, RecommendationPlaylist) and playlist.infinite:
            self._tag.setText("ПОТОК")
        else:
            self._tag.setText("ПЛЕЙЛИСТ")
        self._count.setText(self._tracks_label(self._vm.track_count))
        self._cover.set_content(playlist.name, playlist_cover_path(playlist))

    def _on_covers_ready(self) -> None:
        self._sync_header()
        self._table.viewport().update()

    def showEvent(self, event: QEvent) -> None:
        super().showEvent(event)
        self._table._sync_column_width()
        self._table.viewport().update()

    @staticmethod
    def _tracks_label(count: int) -> str:
        if count % 10 == 1 and count % 100 != 11:
            suffix = "трек"
        elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
            suffix = "трека"
        else:
            suffix = "треков"
        return f"{count} {suffix}"

    def _on_play_all(self) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_all(), self._bridge)

    def _on_shuffle(self) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_shuffled(), self._bridge)

    def _on_play_row(self, index) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_at(index.row()), self._bridge)

    def _on_context_menu(self, pos) -> None:
        if self._bridge is None:
            return
        index = self._table.indexAt(pos)
        if not index.isValid():
            return
        track = self._vm.model.get_track(index.row())
        if track is None:
            return
        menu = QMenu(self)
        menu.setObjectName("playlistPickMenu")
        add_action = QAction("Добавить в плейлист…", menu)
        add_action.triggered.connect(
            lambda: show_add_to_playlist_menu(
                track, bridge=self._bridge, parent=self
            )
        )
        menu.addAction(add_action)
        if self._vm.can_remove_tracks:
            menu.addSeparator()
            remove_action = QAction(self._vm.remove_action_label, menu)
            remove_action.triggered.connect(
                lambda: self._confirm_remove(index.row(), track)
            )
            menu.addAction(remove_action)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _on_delete_selected(self) -> None:
        if not self._vm.can_remove_tracks:
            return
        index = self._table.currentIndex()
        if not index.isValid():
            return
        track = self._vm.model.get_track(index.row())
        if track is None:
            return
        self._confirm_remove(index.row(), track)

    def _confirm_remove(self, row: int, track) -> None:
        if self._bridge is None:
            return
        title, text = self._vm.remove_confirm_text(track)
        answer = QMessageBox.question(
            self,
            title,
            text,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        schedule(self._vm.remove_track_at(row), self._bridge)

    def set_playing_track(self, track) -> None:
        self._vm.set_playing_track(track)
