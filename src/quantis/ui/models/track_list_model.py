"""UI model списка треков с ленивой подгрузкой строк."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from quantis.models.track import Track


class TrackListModel(QAbstractTableModel):
    TrackRole = Qt.ItemDataRole.UserRole + 1
    IndexRole = Qt.ItemDataRole.UserRole + 2
    IsPlayingRole = Qt.ItemDataRole.UserRole + 3

    DEFAULT_BATCH_SIZE = 40

    def __init__(
        self,
        tracks: list[Track] | None = None,
        *,
        batch_size: int | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._batch_size = max(1, batch_size or self.DEFAULT_BATCH_SIZE)
        self._tracks: list[Track] = list(tracks or [])
        self._loaded_count = min(len(self._tracks), self._batch_size)
        self._playing_track: Track | None = None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TrackRole: b"track",
            self.IndexRole: b"index",
            self.IsPlayingRole: b"isPlaying",
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return self._loaded_count

    def columnCount(self, parent=QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid() or not (0 <= index.row() < self._loaded_count):
            return None

        track = self._tracks[index.row()]

        if role == self.TrackRole:
            return track
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{track.title} — {track.author}"
        if role == self.IndexRole:
            return index.row() + 1
        if role == self.IsPlayingRole:
            return self._playing_track is not None and track == self._playing_track
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def canFetchMore(self, parent: QModelIndex) -> bool:
        if parent.isValid():
            return False
        return self._loaded_count < len(self._tracks)

    def fetchMore(self, parent: QModelIndex) -> None:
        if parent.isValid():
            return
        remaining = len(self._tracks) - self._loaded_count
        if remaining <= 0:
            return
        count = min(remaining, self._batch_size)
        start = self._loaded_count
        end = start + count - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._loaded_count += count
        self.endInsertRows()

    def set_tracks(self, tracks: list[Track]) -> None:
        # Передаём ownership списка — без лишнего list()-копирования.
        self.beginResetModel()
        self._tracks = tracks if isinstance(tracks, list) else list(tracks)
        self._loaded_count = min(len(self._tracks), self._batch_size)
        self.endResetModel()

    def append_tracks(self, tracks: list[Track]) -> None:
        extra = [track for track in tracks if track not in self._tracks]
        if not extra:
            return
        start = self._loaded_count
        end = start + len(extra) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._tracks.extend(extra)
        self._loaded_count += len(extra)
        self.endInsertRows()

    def all_tracks(self) -> list[Track]:
        return self._tracks

    def clear(self) -> None:
        self.set_tracks([])

    def get_track(self, index: int) -> Track | None:
        if 0 <= index < len(self._tracks):
            return self._tracks[index]
        return None

    def remove_track(self, index: int) -> bool:
        if not (0 <= index < len(self._tracks)):
            return False

        was_visible = index < self._loaded_count
        if was_visible:
            self.beginRemoveRows(QModelIndex(), index, index)
        self._tracks.pop(index)
        if was_visible:
            self._loaded_count = max(0, self._loaded_count - 1)
            self.endRemoveRows()
        return True

    def set_playing_track(self, track: Track | None) -> None:
        if self._playing_track is track:
            return
        rows: set[int] = set()
        if self._playing_track is not None:
            try:
                rows.add(self._tracks.index(self._playing_track))
            except ValueError:
                pass
        self._playing_track = track
        if track is not None:
            try:
                rows.add(self._tracks.index(track))
            except ValueError:
                pass
        role = [self.IsPlayingRole]
        for row in rows:
            if row < self._loaded_count:
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, role)
