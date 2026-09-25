from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from quantis.models.playlist import Playlist
from quantis.ui.views.widgets.cover_art import (
    load_cover_pixmap,
    paint_rounded_cover,
    playlist_cover_path,
)


class GradientCover(QWidget):
    """Обложка: файл или градиент с буквой."""

    def __init__(
        self,
        name: str,
        *,
        size: int = 140,
        image_path: str | None = None,
        radius: int = 16,
        source_key: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._image_path = image_path
        self._size = size
        self._radius = radius
        self._source_key = source_key
        self._play_overlay = False
        self._pixmap: QPixmap | None = None
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._reload_pixmap()

    def set_content(
        self,
        name: str,
        image_path: str | None = None,
        source_key: str | None = None,
    ) -> None:
        changed = False
        if source_key is not None and source_key != self._source_key:
            self._source_key = source_key
            changed = True
        if self._name != name or self._image_path != image_path:
            self._name = name
            self._image_path = image_path
            self._reload_pixmap()
            changed = True
        if changed:
            self.update()

    def set_name(self, name: str) -> None:
        self.set_content(name, self._image_path)

    def set_play_overlay(self, show: bool) -> None:
        if self._play_overlay == show:
            return
        self._play_overlay = show
        self.update()

    def set_display_size(self, size: int) -> None:
        size = max(64, int(size))
        if self.width() == size and self.height() == size:
            return
        self.setFixedSize(size, size)

    def _reload_pixmap(self) -> None:
        self._pixmap = load_cover_pixmap(self._image_path, self._size)

    def _is_icon_cover(self) -> bool:
        return bool(self._image_path) and str(self._image_path).lower().endswith(".svg")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = self.rect()
        if self._is_icon_cover() and self._pixmap is not None:
            # SVG-иконки системных подборок — контур на прозрачном фоне:
            # во весь квадрат они упираются в края, поэтому рисуем с полями.
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            backdrop = QPainterPath()
            backdrop.addRoundedRect(rect, self._radius, self._radius)
            painter.fillPath(backdrop, QColor(255, 255, 255, 14))
            inset = round(rect.width() * 0.2)
            painter.drawPixmap(
                rect.adjusted(inset, inset, -inset, -inset), self._pixmap
            )
        else:
            paint_rounded_cover(
                painter,
                rect,
                label=self._name,
                pixmap=self._pixmap,
                source_key=self._source_key,
                radius=self._radius,
            )
        if self._play_overlay:
            overlay = QPainterPath()
            overlay.addRoundedRect(rect, self._radius, self._radius)
            painter.fillPath(overlay, QColor(0, 0, 0, 118))
            size = max(26, rect.width() // 4)
            play = rect.adjusted(
                (rect.width() - size) // 2,
                (rect.height() - size) // 2,
                -(rect.width() - size) // 2,
                -(rect.height() - size) // 2,
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(248, 250, 252, 235))
            painter.drawEllipse(play)
            painter.setPen(QColor(11, 13, 18))
            font = QFont("Bahnschrift", max(9, size // 3), QFont.Weight.Bold)
            painter.setFont(font)
            painter.drawText(
                play.adjusted(1, 0, 1, 0),
                Qt.AlignmentFlag.AlignCenter,
                "▶",
            )
        painter.end()


def wrap_column_count(width: int, min_item_width: int, spacing: int, count: int) -> int:
    """Сколько колонок влезает в ширину, не больше числа карточек."""
    if count <= 0:
        return 1
    if width <= 0:
        return min(count, 1)
    cols = max(1, (width + spacing) // (min_item_width + spacing))
    return min(cols, count)


def playlist_tracks_label(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        suffix = "трек"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        suffix = "трека"
    else:
        suffix = "треков"
    return f"{count} {suffix}"


class PlaylistCard(QFrame):
    """Карточка плейлиста: квадрат обложки + одна строка названия."""

    TITLE_H = 22
    GAP = 8

    activated = Signal(object)

    def __init__(self, playlist: Playlist, parent=None) -> None:
        super().__init__(parent)
        self._playlist = playlist
        self._title_text = playlist.name
        self.setObjectName("playlistCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.GAP)

        self._cover = GradientCover(
            playlist.name,
            size=160,
            image_path=playlist_cover_path(playlist),
            radius=16,
        )
        layout.addWidget(self._cover)

        self._title = QLabel(playlist.name)
        self._title.setObjectName("playlistCardTitle")
        self._title.setWordWrap(False)
        self._title.setFixedHeight(self.TITLE_H)
        layout.addWidget(self._title)

    @property
    def playlist(self) -> Playlist:
        return self._playlist

    def apply_cell(self, width: int, height: int) -> None:
        self._cover.set_display_size(width)
        metrics = QFontMetrics(self._title.font())
        self._title.setText(
            metrics.elidedText(
                self._title_text, Qt.TextElideMode.ElideRight, max(32, width - 2)
            )
        )
        self.setFixedSize(width, height)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._playlist)
        super().mouseReleaseEvent(event)

    def enterEvent(self, event) -> None:
        self.setProperty("hovered", True)
        self._cover.set_play_overlay(True)
        self.style().unpolish(self)
        self.style().polish(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.setProperty("hovered", False)
        self._cover.set_play_overlay(False)
        self.style().unpolish(self)
        self.style().polish(self)
        super().leaveEvent(event)


class QuickPickTile(QFrame):
    """Стеклянная плитка быстрого доступа — как карточка «Моя волна»."""

    activated = Signal(object)

    def __init__(self, playlist: Playlist, parent=None) -> None:
        super().__init__(parent)
        self._playlist = playlist
        self._hovered = False
        self.setObjectName("quickPickTile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(188)
        self.setFixedHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 14, 0)
        layout.setSpacing(0)

        self._thumb = GradientCover(
            playlist.name,
            size=72,
            image_path=playlist_cover_path(playlist),
            radius=14,
        )
        layout.addWidget(self._thumb)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(14, 0, 0, 0)
        text_col.setSpacing(0)
        self._title = QLabel(playlist.name)
        self._title.setObjectName("quickPickTitle")
        self._title.setWordWrap(False)
        self._title.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        text_col.addStretch(1)
        text_col.addWidget(self._title)
        text_col.addStretch(1)
        layout.addLayout(text_col, stretch=1)

    @property
    def playlist(self) -> Playlist:
        return self._playlist

    def apply_cell(self, width: int, height: int) -> None:
        self.setFixedSize(width, height)
        metrics = QFontMetrics(self._title.font())
        self._title.setText(
            metrics.elidedText(
                self._playlist.name,
                Qt.TextElideMode.ElideRight,
                max(32, width - 92),
            )
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        painter.fillPath(path, QColor(255, 255, 255, 18 if self._hovered else 10))
        pen = QPen(QColor(46, 230, 255, 88 if self._hovered else 40))
        pen.setWidthF(1.1)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.end()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._thumb.set_play_overlay(True)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._thumb.set_play_overlay(False)
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._playlist)
        super().mouseReleaseEvent(event)


class WrapGrid(QWidget):
    """Сетка по координатам: без QGridLayout и без «призрачных» рядов."""

    def __init__(
        self,
        *,
        min_item_width: int,
        spacing: int = 12,
        fixed_row_height: int | None = None,
        caption_height: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min_item_width = min_item_width
        self._spacing = spacing
        self._fixed_row_height = fixed_row_height
        self._caption_height = caption_height
        self._items: list[QWidget] = []
        self._reflowing = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_widgets(self, widgets: list[QWidget]) -> None:
        for old in self._items:
            old.setParent(None)
            old.deleteLater()
        self._items = widgets
        for widget in widgets:
            widget.setParent(self)
            widget.show()
        self._reflow()
        QTimer.singleShot(0, self._reflow)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._height_for(width)

    def sizeHint(self) -> QSize:
        width = max(self.width(), self._min_item_width)
        return QSize(width, self._height_for(width))

    def minimumSizeHint(self) -> QSize:
        row = self._row_height(self._min_item_width)
        return QSize(self._min_item_width, row if self._items else 0)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reflow()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._reflow()
        QTimer.singleShot(0, self._reflow)

    def _cell_width(self, width: int, cols: int) -> int:
        if cols <= 0:
            return self._min_item_width
        return max(1, (width - self._spacing * (cols - 1)) // cols)

    def _row_height(self, cell_width: int) -> int:
        if self._fixed_row_height is not None:
            return self._fixed_row_height
        return cell_width + self._caption_height

    def _height_for(self, width: int) -> int:
        count = len(self._items)
        if count == 0 or width <= 0:
            return 0
        cols = wrap_column_count(width, self._min_item_width, self._spacing, count)
        cell_w = self._cell_width(width, cols)
        rows = (count + cols - 1) // cols
        row_h = self._row_height(cell_w)
        return rows * row_h + max(0, rows - 1) * self._spacing

    def _reflow(self) -> None:
        if self._reflowing:
            return
        count = len(self._items)
        if count == 0:
            if self.height() != 0:
                self.setFixedHeight(0)
            return
        width = self.width()
        if width <= 1:
            parent = self.parentWidget()
            if parent is not None:
                width = parent.width()
        if width <= 1:
            return

        self._reflowing = True
        try:
            cols = wrap_column_count(width, self._min_item_width, self._spacing, count)
            cell_w = self._cell_width(width, cols)
            row_h = self._row_height(cell_w)
            for index, widget in enumerate(self._items):
                col = index % cols
                row = index // cols
                apply = getattr(widget, "apply_cell", None)
                if apply is not None:
                    apply(cell_w, row_h)
                widget.setGeometry(
                    col * (cell_w + self._spacing),
                    row * (row_h + self._spacing),
                    cell_w,
                    row_h,
                )
            total = self._height_for(width)
            if self.height() != total:
                self.setFixedHeight(total)
                self.updateGeometry()
        finally:
            self._reflowing = False


class QuickPickShelf(QWidget):
    """Сетка быстрых плиток — как recently played, без ползунка."""

    playlist_activated = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("quickPickShelf")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._empty = QLabel("Появится после первых прослушиваний")
        self._empty.setObjectName("homeEmptyHint")
        self._empty.setWordWrap(True)
        self._empty.hide()

        self._grid = WrapGrid(min_item_width=200, spacing=10, fixed_row_height=72)
        self._grid.setObjectName("quickPickShelfHost")
        outer.addWidget(self._empty)
        outer.addWidget(self._grid)

    def set_playlists(self, playlists: list[Playlist]) -> None:
        if not playlists:
            self._grid.set_widgets([])
            self._grid.hide()
            self._empty.show()
            return
        self._empty.hide()
        self._grid.show()
        tiles: list[QWidget] = []
        for playlist in playlists:
            tile = QuickPickTile(playlist)
            tile.activated.connect(self.playlist_activated.emit)
            tiles.append(tile)
        self._grid.set_widgets(tiles)


class PlaylistShelf(QWidget):
    """Сетка обложек плейлистов — перестраивается по ширине окна."""

    playlist_activated = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playlistShelf")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._empty = QLabel("Создай первый плейлист")
        self._empty.setObjectName("homeEmptyHint")
        self._empty.setWordWrap(True)
        self._empty.hide()

        self._grid = WrapGrid(
            min_item_width=136,
            spacing=14,
            caption_height=PlaylistCard.GAP + PlaylistCard.TITLE_H,
        )
        self._grid.setObjectName("playlistShelfHost")
        outer.addWidget(self._empty)
        outer.addWidget(self._grid)

    def set_playlists(self, playlists: list[Playlist]) -> None:
        if not playlists:
            self._grid.set_widgets([])
            self._grid.hide()
            self._empty.show()
            return
        self._empty.hide()
        self._grid.show()
        cards: list[QWidget] = []
        for playlist in playlists:
            card = PlaylistCard(playlist)
            card.activated.connect(self.playlist_activated.emit)
            cards.append(card)
        self._grid.set_widgets(cards)
