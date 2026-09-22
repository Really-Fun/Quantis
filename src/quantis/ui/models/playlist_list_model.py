"""Модель списка плейлистов для таблиц на главной."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from quantis.models.playlist import Playlist


class PlaylistListModel(QAbstractTableModel):
    PlaylistRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._playlists: list[Playlist] = []

    def set_playlists(self, playlists: list[Playlist]) -> None:
        self.beginResetModel()
        self._playlists = list(playlists)
        self.endResetModel()

    def playlist_at(self, row: int) -> Playlist | None:
        if 0 <= row < len(self._playlists):
            return self._playlists[row]
        return None

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._playlists)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._playlists)):
            return None
        playlist = self._playlists[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return playlist.name
        if role == self.PlaylistRole:
            return playlist
        return None
