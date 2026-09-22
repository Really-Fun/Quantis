from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.ui.async_ui import schedule
from quantis.ui.playlist_actions import show_add_to_playlist_menu
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.widgets.home_section import HomeSection
from quantis.ui.views.widgets.track_card import TrackCardDelegate


class LibraryPage(QWidget):
    def __init__(
        self,
        view_model: HomeViewModel,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._bridge = bridge
        self.setObjectName("libraryPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 24)
        layout.setSpacing(8)

        section = HomeSection("Скачанные", "Треки, которые можно слушать офлайн")
        host = QWidget()
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(0)

        self._list = QTableView()
        self._list.setObjectName("trackList")
        self._list.setModel(self._vm.downloaded_model)
        self._list.verticalHeader().hide()
        self._list.horizontalHeader().hide()
        self._list.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self._list.verticalHeader().setDefaultSectionSize(TrackCardDelegate.CARD_HEIGHT)
        self._list.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self._list.setShowGrid(False)
        self._list.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._list.setItemDelegate(TrackCardDelegate(self._list))
        self._list.setMouseTracking(True)
        self._list.viewport().setMouseTracking(True)
        self._list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu)
        self._list.doubleClicked.connect(self._on_play)
        delete = QShortcut(QKeySequence.StandardKey.Delete, self._list)
        delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        delete.activated.connect(self._on_delete_selected)

        self._empty = QLabel("Скачай трек из плеера — он появится здесь")
        self._empty.setObjectName("homeEmptyHint")
        self._empty.setWordWrap(True)

        host_layout.addWidget(self._list, stretch=1)
        host_layout.addWidget(self._empty)
        section.add_widget_block(host, expand=True)
        layout.addWidget(section, stretch=1)

        self._vm.downloaded_changed.connect(self._sync_empty)
        self._sync_empty()

    def _sync_empty(self) -> None:
        empty = self._vm.downloaded_model.rowCount() == 0
        self._empty.setVisible(empty)
        self._list.setVisible(not empty)

    def _on_play(self, index) -> None:
        if self._bridge is not None:
            schedule(self._vm.play_downloaded_at(index.row()), self._bridge)

    def _on_context_menu(self, pos) -> None:
        if self._bridge is None:
            return
        index = self._list.indexAt(pos)
        if not index.isValid():
            return
        track = self._vm.downloaded_model.get_track(index.row())
        if track is None:
            return
        menu = QMenu(self)
        menu.setObjectName("playlistPickMenu")
        add_action = QAction("Добавить в плейлист…", menu)
        add_action.triggered.connect(
            lambda: show_add_to_playlist_menu(track, bridge=self._bridge, parent=self)
        )
        menu.addAction(add_action)
        menu.addSeparator()
        remove_action = QAction("Удалить скачанный файл", menu)
        remove_action.triggered.connect(
            lambda: self._confirm_remove(index.row(), track)
        )
        menu.addAction(remove_action)
        menu.exec(self._list.viewport().mapToGlobal(pos))

    def _on_delete_selected(self) -> None:
        index = self._list.currentIndex()
        if not index.isValid():
            return
        track = self._vm.downloaded_model.get_track(index.row())
        if track is None:
            return
        self._confirm_remove(index.row(), track)

    def _confirm_remove(self, row: int, track) -> None:
        if self._bridge is None:
            return
        answer = QMessageBox.question(
            self,
            "Удалить файл",
            f"Удалить «{track.title}» с диска? Файл нельзя будет слушать офлайн.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        schedule(self._vm.remove_downloaded_at(row), self._bridge)

    def set_playing_track(self, track) -> None:
        self._vm.downloaded_model.set_playing_track(track)
        self._sync_empty()
