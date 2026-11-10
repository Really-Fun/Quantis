"""Делегат строки плейлиста: # / обложка+badge / название · источник / длина.

Строки лежат на арте подборки, поэтому у них своя скруглённая подложка."""

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from quantis.models.track import Track
from quantis.ui.corners import corner
from quantis.ui.models import TrackListModel
from quantis.ui.preferences import UiPreferences
from quantis.ui.resources import format_ms
from quantis.ui.themes.spec import qcolor
from quantis.ui.views.widgets.cover_art import (
    CoverDecoder,
    paint_rounded_cover,
    request_track_cover,
)
from quantis.ui.views.widgets.delegate_paint_kit import (
    SOURCE_LABELS,
    paint_colors,
    paint_fonts,
)


class PlaylistTrackDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 56
    INDEX_WIDTH = 36
    COVER_SIZE = 40
    DURATION_WIDTH = 48

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._prefs = UiPreferences()
        CoverDecoder.instance().ready.connect(self._on_cover_ready)
        self._prefs.theme_changed.connect(self._on_theme_changed)

    def _on_cover_ready(self) -> None:
        view = self.parent()
        if view is not None and hasattr(view, "viewport"):
            view.viewport().update()

    def _on_theme_changed(self) -> None:
        parent = self.parent()
        if parent is not None and hasattr(parent, "viewport"):
            parent.viewport().update()
        elif parent is not None:
            parent.update()

    def sizeHint(self, option, index) -> QSize:
        width = 320
        view = option.widget
        if view is not None and hasattr(view, "viewport"):
            width = max(view.viewport().width(), width)
        return QSize(width, self.ROW_HEIGHT)

    def _cover_pixmap(self, track: Track):
        return request_track_cover(track, self.COVER_SIZE)

    def paint(self, painter: QPainter, option, index) -> None:
        track = index.data(TrackListModel.TrackRole)
        if track is None:
            return

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        is_playing = bool(index.data(TrackListModel.IsPlayingRole))
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        row = index.row()
        rect = option.rect

        colors = paint_colors(self._prefs.theme)
        fonts = paint_fonts(self._prefs.theme)
        plate = QRectF(rect).adjusted(0, 1, 0, -1)
        radius = corner(10)
        painter.setPen(Qt.PenStyle.NoPen)
        # Плашка цветом темы: текст читается и на светлом арте; через одну плотнее.
        backing = qcolor(self._prefs.theme.colors.bg)
        backing.setAlpha(120 if row % 2 == 0 else 64)
        painter.setBrush(backing)
        painter.drawRoundedRect(plate, radius, radius)
        if is_playing:
            painter.setBrush(colors.bg_playing)
            painter.drawRoundedRect(plate, radius, radius)
            painter.setBrush(colors.accent)
            painter.drawRoundedRect(
                QRectF(rect.left(), rect.top() + 14, 3, rect.height() - 28), 1.5, 1.5
            )
        elif hovered or selected:
            painter.setBrush(colors.bg_hover)
            painter.drawRoundedRect(plate, radius, radius)

        inner = rect.adjusted(8, 0, -8, 0)
        idx_rect = QRect(inner.left(), inner.top(), self.INDEX_WIDTH, inner.height())
        cover_rect = QRect(
            idx_rect.right() + 10,
            inner.top() + (inner.height() - self.COVER_SIZE) // 2,
            self.COVER_SIZE,
            self.COVER_SIZE,
        )
        text_left = cover_rect.right() + 12
        text_right = inner.right()
        if track.duration_ms > 0:
            duration_rect = QRect(
                inner.right() - self.DURATION_WIDTH - 4,
                inner.top(),
                self.DURATION_WIDTH,
                inner.height(),
            )
            text_right = duration_rect.left() - 12
            painter.setFont(fonts.author)
            painter.setPen(colors.title_playing if is_playing else colors.title)
            painter.drawText(
                duration_rect,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                format_ms(track.duration_ms),
            )
        text_w = max(0, text_right - text_left)

        painter.setFont(fonts.index)
        painter.setPen(colors.index_playing if is_playing else colors.index)
        painter.drawText(idx_rect, Qt.AlignmentFlag.AlignCenter, f"{row + 1}")

        paint_rounded_cover(
            painter,
            cover_rect,
            label=track.title or track.author or "?",
            pixmap=self._cover_pixmap(track),
            source_key=str(track.source),
            with_badge=True,
        )

        if hovered and not is_playing:
            painter.fillRect(cover_rect, QColor(0, 0, 0, 110))
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(cover_rect, Qt.AlignmentFlag.AlignCenter, "▶")

        title_rect = QRect(text_left, inner.top() + 11, text_w, 20)
        author_rect = QRect(text_left, inner.top() + 30, text_w, 16)

        painter.setFont(fonts.title)
        painter.setPen(colors.title_playing if is_playing else colors.title)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fonts.fm_title.elidedText(
                track.title or "—",
                Qt.TextElideMode.ElideRight,
                text_w,
            ),
        )

        source_key = str(track.source).lower()
        badge = SOURCE_LABELS.get(source_key, "")
        subtitle = track.author or "—"
        if badge:
            subtitle = f"{subtitle} · {badge}"

        painter.setFont(fonts.author)
        painter.setPen(colors.subtitle)
        painter.drawText(
            author_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            fonts.fm_author.elidedText(subtitle, Qt.TextElideMode.ElideRight, text_w),
        )
        painter.restore()
