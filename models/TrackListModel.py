"""Модель списка треков для QListView."""

from PySide6.QtCore import QAbstractListModel, Qt, QModelIndex
from typing import List, Optional
from models import Track


class TrackListModel(QAbstractListModel):
    TrackRole = Qt.UserRole + 1
    IndexRole = Qt.UserRole + 2
    IsPlayingRole = Qt.UserRole + 3

    def __init__(self, tracks: Optional[List[Track]] = None, parent=None):
        super().__init__(parent)
        self._tracks = tracks or []
        self._playing_track: Optional[Track] = None

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._tracks)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> any:
        if not index.isValid() or not (0 <= index.row() < len(self._tracks)):
            return None

        track = self._tracks[index.row()]

        if role == self.TrackRole:
            return track
        elif role == self.IndexRole:
            return index.row() + 1
        elif role == self.IsPlayingRole:
            return self._playing_track is not None and track == self._playing_track
        return None

    def set_tracks(self, tracks: List[Track]):
        self.beginResetModel()
        self._tracks = tracks
        self.endResetModel()

    def get_track(self, index: int) -> Optional[Track]:
        if 0 <= index < len(self._tracks):
            return self._tracks[index]
        return None

    def remove_track(self, index: int) -> bool:
        if 0 <= index < len(self._tracks):
            self.beginRemoveRows(QModelIndex(), index, index)
            self._tracks.pop(index)
            self.endRemoveRows()
            return True
        return False

    def set_playing_track(self, track: Optional[Track]):
        self._playing_track = track
        self.dataChanged.emit(
            self.index(0), self.index(self.rowCount() - 1), [self.IsPlayingRole]
        )
