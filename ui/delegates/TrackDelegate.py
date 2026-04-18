"""
Делегат для рендеринга карточки трека в QListView.

Заменяет тяжелые виджеты QWidget (TrackCard) на быструю отрисовку через QPainter.
"""

from PySide6.QtCore import Qt, QRectF, QSize, Signal, QObject, QEvent
from PySide6.QtGui import (
    QColor,
    QPainter,
    QFont,
    QIcon,
    QPixmap,
    QPainterPath,
)
from PySide6.QtWidgets import (
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)

from models import TrackListModel, Track
import os

_COVER_SIZE = 48
_CARD_HEIGHT = 60
_BORDER_RADIUS = 10
_SOURCE_COLORS = {
    "yandex": QColor(0, 220, 255, 140),
    "youtube": QColor(255, 60, 60, 140),
}
_DEFAULT_SOURCE_COLOR = QColor(160, 160, 160, 140)


class TrackDelegateSignals(QObject):
    play_requested = Signal(object)  # Track
    download_requested = Signal(object)  # Track
    add_to_playlist_requested = Signal(object)  # Track
    remove_from_playlist_requested = Signal(object)  # Track
    context_menu_requested = Signal(object, object)  # Track, global_pos


class TrackDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = TrackDelegateSignals(self)
        self._hovered_row = -1

        # Load paths providers/downloaders externally or pass them,
        # but for simple paint we just load the pixmap if exists.
        from providers import PathProvider

        self._path_provider = PathProvider()

        # We need icons
        from utils import asset_path

        self._play_icon = QIcon(asset_path("assets/icons/play.png"))
        self._dl_icon = QIcon(asset_path("assets/icons/download.png"))

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        return QSize(option.rect.width(), _CARD_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        painter.save()
        try:
            painter.setRenderHint(QPainter.Antialiasing, True)

            track = index.data(TrackListModel.TrackRole)
            track_index = index.data(TrackListModel.IndexRole)
            is_playing = index.data(TrackListModel.IsPlayingRole)

            if not track:
                return

            rect = QRectF(option.rect)

            # Background & Hover
            is_hovered = option.state & QStyle.State_MouseOver

            if is_playing:
                painter.setBrush(QColor(0, 220, 255, 35))
            elif is_hovered:
                painter.setBrush(QColor(0, 220, 255, 20))
            else:
                painter.setBrush(QColor(255, 255, 255, 6))

            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(
                rect.adjusted(2, 2, -2, -2), _BORDER_RADIUS, _BORDER_RADIUS
            )

            # Internal margins
            margin_x = 10
            margin_y = 6
            spacing = 12
            current_x = rect.left() + margin_x

            # Index or Play Icon
            index_rect = QRectF(
                current_x, rect.top() + margin_y, 22, _CARD_HEIGHT - 2 * margin_y
            )
            if is_playing:
                painter.setPen(QColor(0, 220, 255))
                font = painter.font()
                font.setPointSize(10)
                font.setBold(True)
                painter.setFont(font)
                painter.drawText(index_rect, Qt.AlignCenter, "▶")
            else:
                painter.setPen(QColor(255, 255, 255, 80))
                font = painter.font()
                font.setPixelSize(13)
                painter.setFont(font)
                painter.drawText(index_rect, Qt.AlignCenter, str(track_index))

            current_x += 22 + spacing

            # Cover
            cover_rect = QRectF(
                current_x,
                rect.top() + (_CARD_HEIGHT - _COVER_SIZE) / 2,
                _COVER_SIZE,
                _COVER_SIZE,
            )

            # Try to load cover synchronous if exists
            path = self._path_provider.get_cover_path(track)
            if os.path.exists(path):
                pixmap = QPixmap(path).scaled(
                    _COVER_SIZE,
                    _COVER_SIZE,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                # Clip
                path_clip = QPainterPath()
                path_clip.addRoundedRect(cover_rect, _COVER_SIZE // 4, _COVER_SIZE // 4)
                painter.setClipPath(path_clip)
                painter.drawPixmap(cover_rect.topLeft(), pixmap)
                painter.setClipping(False)
            else:
                # Placeholder
                painter.setBrush(QColor(26, 26, 26))
                painter.drawRoundedRect(cover_rect, _COVER_SIZE // 4, _COVER_SIZE // 4)

            # Hover Overlay for Cover (Play Button)
            if is_hovered:
                painter.setBrush(QColor(0, 0, 0, 140))
                painter.drawRoundedRect(cover_rect, _COVER_SIZE // 4, _COVER_SIZE // 4)
                icon_rect = QRectF(
                    cover_rect.center().x() - 11, cover_rect.center().y() - 11, 22, 22
                )
                self._play_icon.paint(painter, icon_rect.toRect(), Qt.AlignCenter)

            current_x += _COVER_SIZE + spacing

            # Text Block (Title / Author)
            right_panel_width = 80  # approx source + dl btn width
            text_width = rect.right() - right_panel_width - current_x
            text_rect = QRectF(
                current_x,
                rect.top() + margin_y,
                text_width,
                _CARD_HEIGHT - 2 * margin_y,
            )

            title_rect = QRectF(
                text_rect.left(), text_rect.top() + 4, text_rect.width(), 20
            )
            author_rect = QRectF(
                text_rect.left(), text_rect.top() + 24, text_rect.width(), 20
            )

            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPixelSize(14)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)

            fm = painter.fontMetrics()
            elided_title = fm.elidedText(track.title, Qt.ElideRight, text_rect.width())
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

            painter.setPen(QColor(255, 255, 255, 120))
            font = painter.font()
            font.setPixelSize(12)
            font.setWeight(QFont.Weight.Normal)
            painter.setFont(font)

            author_str = self._build_meta_line(track)
            fm_auth = painter.fontMetrics()
            elided_author = fm_auth.elidedText(
                author_str, Qt.ElideRight, text_rect.width()
            )
            painter.drawText(author_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_author)

            # Download Button & Source Badge
            current_right = rect.right() - margin_x

            # Source badge is drawn only if not hovered OR if hovered, but we ensure both fit.
            # Download button acts when hovered

            if is_hovered:
                # Draw Download btn
                dl_rect = QRectF(
                    rect.right() - margin_x - 28,
                    rect.top() + (_CARD_HEIGHT - 28) / 2,
                    28,
                    28,
                )
                painter.setBrush(QColor(255, 255, 255, 15))
                painter.drawRoundedRect(dl_rect, 14, 14)
                self._dl_icon.paint(
                    painter, dl_rect.adjusted(6, 6, -6, -6).toRect(), Qt.AlignCenter
                )
                current_right -= 28 + spacing

            # Draw Source Badge
            source_color = _SOURCE_COLORS.get(track.source, _DEFAULT_SOURCE_COLOR)
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPixelSize(11)
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)

            fm = painter.fontMetrics()
            source_w = fm.horizontalAdvance(track.source) + 16
            source_h = 22
            source_rect = QRectF(
                current_right - source_w,
                rect.top() + (_CARD_HEIGHT - source_h) / 2,
                source_w,
                source_h,
            )

            painter.setBrush(source_color)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(source_rect, 6, 6)

            painter.setPen(QColor(255, 255, 255))
            painter.drawText(source_rect, Qt.AlignCenter, track.source)
        finally:
            painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress:
            track = index.data(TrackListModel.TrackRole)
            if not track:
                return False

            pos = event.position()
            rect = option.rect
            margin_x = 10
            spacing = 12
            current_x = rect.left() + margin_x + 22 + spacing
            cover_rect = QRectF(
                current_x,
                rect.top() + (_CARD_HEIGHT - _COVER_SIZE) / 2,
                _COVER_SIZE,
                _COVER_SIZE,
            )

            dl_rect = QRectF(
                rect.right() - margin_x - 28,
                rect.top() + (_CARD_HEIGHT - 28) / 2,
                28,
                28,
            )

            if event.button() == Qt.LeftButton:
                if cover_rect.contains(pos) or not dl_rect.contains(pos):
                    # Play clicked anywhere on card (except download btn)
                    self.signals.play_requested.emit(track)
                    return True
                elif dl_rect.contains(pos):
                    # Download clicked
                    self.signals.download_requested.emit(track)
                    return True
            elif event.button() == Qt.RightButton:
                self.signals.context_menu_requested.emit(
                    track, event.globalPosition().toPoint()
                )
                return True

        # To make hover work in list view without mouse tracking issues, you usually set
        # view.setMouseTracking(True) where you use the delegate.
        return super().editorEvent(event, model, option, index)

    @staticmethod
    def _build_meta_line(track: Track) -> str:
        listens = max(0, int(getattr(track, "listen_count", 0)))
        if listens == 0:
            return track.author
        tail_100 = listens % 100
        tail_10 = listens % 10
        if 11 <= tail_100 <= 14:
            word = "прослушиваний"
        elif tail_10 == 1:
            word = "прослушивание"
        elif 2 <= tail_10 <= 4:
            word = "прослушивания"
        else:
            word = "прослушиваний"
        return f"{track.author} · {listens} {word}"
