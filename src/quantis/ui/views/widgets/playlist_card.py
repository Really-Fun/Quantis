from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.models.playlist import Playlist
from quantis.ui.corners import corner
from quantis.ui.fonts import app_font
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor
from quantis.ui.views.widgets.art_card import ArtCard, CoverSource
from quantis.ui.views.widgets.cover_art import (
    load_cover_pixmap,
    paint_rounded_cover,
    playlist_cover_path,
)
from quantis.utils.get_ru_words import get_ru_words_for_number


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
            backdrop.addRoundedRect(rect, corner(self._radius), corner(self._radius))
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
            overlay.addRoundedRect(rect, corner(self._radius), corner(self._radius))
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
            font = app_font(max(9, size // 3), QFont.Weight.Bold)
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


_BALANCED_MAX_ITEM = 320


def balanced_column_count(
    width: int, min_item_width: int, spacing: int, count: int
) -> int:
    """Колонки, при которых ряды заполнены поровну (6 при 5 местах — 3 + 3).

    Если всё влезает в один ряд, плитки растягиваются на весь ряд, но не
    шире ``_BALANCED_MAX_ITEM``: одна плитка не занимает всю ширину, а шесть
    на широком окне не оставляют пустое место справа.
    """
    if count <= 0 or width <= 0:
        return 1
    fit = max(1, (width + spacing) // (min_item_width + spacing))
    if count <= fit:
        narrowest = -(-(width + spacing) // (_BALANCED_MAX_ITEM + spacing))
        return min(fit, max(count, narrowest))
    rows = (count + fit - 1) // fit
    return (count + rows - 1) // rows


def playlist_tracks_label(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        suffix = "трек"
    elif count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        suffix = "трека"
    else:
        suffix = "треков"
    return f"{count} {suffix}"


def playlist_card_covers(playlist: Playlist) -> CoverSource:
    """Обложка плейлиста: своя картинка, иначе обложка первого трека."""
    path = playlist_cover_path(playlist)

    def covers(size: int) -> list[QPixmap | None]:
        return [load_cover_pixmap(path, size)]

    return covers


class PlaylistCard(ArtCard):
    """Карточка плейлиста: обложка, название и число треков."""

    TITLE_H = ArtCard.TITLE_H
    GAP = ArtCard.GAP

    def __init__(self, playlist: Playlist, parent: QWidget | None = None) -> None:
        cover = playlist_cover_path(playlist)
        super().__init__(
            playlist,
            title=playlist.name,
            subtitle=playlist_tracks_label(len(playlist)),
            covers=playlist_card_covers(playlist),
            icon_cover=bool(cover) and str(cover).lower().endswith(".svg"),
            parent=parent,
        )
        self.setObjectName("playlistCard")

    @property
    def playlist(self) -> Playlist:
        return self._item  # type: ignore[return-value]


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
        self._text_col = text_col

    @property
    def playlist(self) -> Playlist:
        return self._playlist

    def set_playlist(self, playlist: Playlist) -> None:
        """Тот же плейлист новым объектом (свежие треки) — без пересоздания;
        обложка перечитывается, только если сменился её файл."""
        self._playlist = playlist
        self._thumb.set_content(playlist.name, playlist_cover_path(playlist))

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
        path.addRoundedRect(rect, corner(14), corner(14))
        # Без обводки: плитку отделяет лёгкая подложка цветом «чернил» темы
        # (белая на тёмных, тёмная на светлой), под мышью — чуть плотнее.
        ink = qcolor(UiPreferences().theme.colors.ink_rgb)
        ink.setAlpha(22 if self._hovered else 11)
        painter.fillPath(path, ink)
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


class WaveQuickTile(QuickPickTile):
    """«Моя волна» первой плиткой быстрого доступа: клик — открыть поток,
    кнопка справа — сразу играть; под названием — «N в потоке»."""

    play_requested = Signal()

    def __init__(self, playlist: Playlist, parent=None) -> None:
        super().__init__(playlist, parent)
        self.setObjectName("waveQuickTile")
        self._available = True
        self._subtitle = QLabel("")
        self._subtitle.setObjectName("quickPickSubtitle")
        self._subtitle.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        self._text_col.insertWidget(2, self._subtitle)
        self._play_btn = QToolButton()
        self._play_btn.setObjectName("waveQuickPlay")
        self._play_btn.setText("▶")
        self._play_btn.setToolTip("Слушать «Мою волну»")
        self._play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._play_btn.setFixedSize(36, 36)
        self._play_btn.clicked.connect(self.play_requested.emit)
        self.layout().addWidget(self._play_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def set_state(
        self,
        *,
        available: bool,
        track_count: int = 0,
        loading: bool = False,
        error: str | None = None,
    ) -> None:
        self._available = available
        self._play_btn.setEnabled(available and track_count > 0 and not loading)
        if loading:
            text = "Загружаем…"
        elif error:
            text = error
        elif available and track_count:
            text = f"{get_ru_words_for_number(track_count)} в потоке"
        elif available:
            text = "Пока пусто"
        else:
            text = "Нужен токен Яндекса — раздел «Аккаунты»"
        self._subtitle.setText(text)
        self._subtitle.setToolTip(text)

    def mouseReleaseEvent(self, event) -> None:
        if self._available:
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
        balanced: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = balanced_column_count if balanced else wrap_column_count
        self._min_item_width = min_item_width
        self._spacing = spacing
        self._fixed_row_height = fixed_row_height
        self._caption_height = caption_height
        self._items: list[QWidget] = []
        self._reflowing = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def items(self) -> list[QWidget]:
        return list(self._items)

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
        cols = self._columns(width, self._min_item_width, self._spacing, count)
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
            cols = self._columns(width, self._min_item_width, self._spacing, count)
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
    wave_play_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("quickPickShelf")
        self._wave_tile: WaveQuickTile | None = None
        self._wave_state: dict[str, object] = {"available": False}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._empty = QLabel("Появится после первых прослушиваний")
        self._empty.setObjectName("homeEmptyHint")
        self._empty.setWordWrap(True)
        self._empty.hide()

        self._signature: tuple | None = None
        self._grid = WrapGrid(
            min_item_width=180, spacing=10, fixed_row_height=72, balanced=True
        )
        self._grid.setObjectName("quickPickShelfHost")
        outer.addWidget(self._empty)
        outer.addWidget(self._grid)

    @staticmethod
    def _tile_key(playlist: Playlist) -> tuple:
        """Состав полки: смена треков или обложки плитку не пересоздаёт."""
        return (type(playlist).__name__, getattr(playlist, "kind", None), playlist.name)

    def set_playlists(self, playlists: list[Playlist]) -> None:
        if not playlists:
            self._wave_tile = None
            self._signature = None
            self._grid.set_widgets([])
            self._grid.hide()
            self._empty.show()
            return
        self._empty.hide()
        self._grid.show()
        # «Моя волна» — всегда первой
        ordered = sorted(playlists, key=lambda p: getattr(p, "kind", None) != "wave")
        # Главная зовёт это на каждую смену трека («Недавние»): пересоздание
        # плиток с синхронным декодированием обложек давало рывки 40–60 мс.
        signature = tuple(self._tile_key(p) for p in ordered)
        if signature == self._signature:
            for tile, playlist in zip(self._grid.items(), ordered, strict=True):
                tile.set_playlist(playlist)
            return
        self._signature = signature
        tiles: list[QWidget] = []
        self._wave_tile = None
        for playlist in ordered:
            if getattr(playlist, "kind", None) == "wave":
                wave = WaveQuickTile(playlist)
                wave.play_requested.connect(self.wave_play_requested.emit)
                wave.set_state(**self._wave_state)
                self._wave_tile = wave
                tile: QuickPickTile = wave
            else:
                tile = QuickPickTile(playlist)
            tile.activated.connect(self.playlist_activated.emit)
            tiles.append(tile)
        self._grid.set_widgets(tiles)

    def set_wave_state(self, **state: object) -> None:
        """Состояние плитки «Моя волна» (см. ``WaveQuickTile.set_state``);
        запоминается, если плитки ещё нет."""
        self._wave_state = dict(state)
        if self._wave_tile is not None:
            self._wave_tile.set_state(**state)  # type: ignore[arg-type]

    @property
    def wave_tile(self) -> WaveQuickTile | None:
        return self._wave_tile


def mix_card(mix: object) -> ArtCard:
    """Карточка микса: название крупно на обложке, как у подборок стримингов."""
    from quantis.services.mixes import MixPlaylist
    from quantis.ui.views.widgets.cover_art import request_track_cover

    assert isinstance(mix, MixPlaylist)
    tracks = list(mix.get_tracks())
    artist = mix.mix_id.startswith("artist:")
    # У артиста — его самая слушаемая обложка целиком, у остальных — коллаж.
    picks = tracks[:1] if artist else tracks[:4]

    def covers(size: int) -> list[QPixmap | None]:
        side = size if artist or len(picks) < 4 else max(32, size // 2)
        return [request_track_cover(track, side) for track in picks]

    card = ArtCard(
        mix,
        title=mix.name,
        subtitle=mix.subtitle,
        covers=covers,
        kicker="АРТИСТ" if artist else "МИКС",
        title_on_cover=True,
    )
    card.setObjectName("mixCard")
    return card


class PlaylistShelf(QWidget):
    """Карточки одной лентой со стрелками; «Все» разворачивает сетку.

    Сетка из 18 плейлистов занимала три ряда и сдвигала главную вниз.
    По умолчанию — плейлисты; ``card_factory`` даёт свои карточки (миксы).
    """

    playlist_activated = Signal(object)
    play_requested = Signal(object)
    expanded_changed = Signal(bool)
    RIBBON_CARD = 164

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        card_factory: Callable[[object], ArtCard] | None = None,
        empty_text: str = "Создай первый плейлист",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("playlistShelf")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self._expanded = False
        self._playlists: list[object] = []
        self._factory = card_factory or (lambda item: PlaylistCard(item))  # type: ignore[arg-type]

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._empty = QLabel(empty_text)
        self._empty.setObjectName("homeEmptyHint")
        self._empty.setWordWrap(True)
        self._empty.hide()

        from quantis.ui.views.widgets.scroll_ribbon import ScrollRibbon

        self._ribbon = ScrollRibbon(spacing=8, object_name="playlistRibbon")
        self._ribbon.setFixedHeight(self.RIBBON_CARD + ArtCard.ROW_EXTRA)
        self._ribbon.set_arrow_band(self.RIBBON_CARD)
        self._ribbon_cards: list[ArtCard] = []

        self._grid = WrapGrid(
            min_item_width=144,
            spacing=8,
            caption_height=ArtCard.ROW_EXTRA,
        )
        self._grid.setObjectName("playlistShelfHost")
        outer.addWidget(self._empty)
        outer.addWidget(self._ribbon)
        outer.addWidget(self._grid)
        self._grid.hide()

    @property
    def expanded(self) -> bool:
        return self._expanded

    @property
    def ribbon(self):  # type: ignore[no-untyped-def]
        return self._ribbon

    @property
    def grid(self) -> WrapGrid:
        return self._grid

    def ribbon_cards(self) -> list[ArtCard]:
        return list(self._ribbon_cards)

    def count(self) -> int:
        return len(self._playlists)

    def set_expanded(self, expanded: bool) -> None:
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._rebuild()
        self.expanded_changed.emit(expanded)

    def set_playlists(self, playlists: Sequence[object]) -> None:
        self._playlists = list(playlists)
        self._rebuild()

    def _card(self, item: object) -> ArtCard:
        card = self._factory(item)
        card.activated.connect(self.playlist_activated.emit)
        card.play_requested.connect(self.play_requested.emit)
        return card

    def _rebuild(self) -> None:
        playlists = self._playlists
        self._empty.setVisible(not playlists)
        row = self._ribbon.row
        for card in self._ribbon_cards:
            row.removeWidget(card)
            card.deleteLater()
        self._ribbon_cards = []
        if not playlists:
            self._grid.set_widgets([])
            self._grid.hide()
            self._ribbon.hide()
            return
        if self._expanded:
            # Лента не держит свои карточки, пока видна сетка: один набор.
            self._ribbon.hide()
            self._grid.set_widgets([self._card(p) for p in playlists])
            self._grid.show()
            return
        self._grid.set_widgets([])
        self._grid.hide()
        size = self.RIBBON_CARD
        for index, playlist in enumerate(playlists):
            card = self._card(playlist)
            card.setFixedSize(size, size + ArtCard.ROW_EXTRA)
            row.insertWidget(index, card)
            self._ribbon_cards.append(card)
        self._ribbon.show()
        self._ribbon.scroll_area.horizontalScrollBar().setValue(0)
