"""Делегат строки плейлиста: # / обложка+badge / название · источник."""

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from quantis.models.track import Track
from quantis.ui.models import TrackListModel
from quantis.ui.preferences import UiPreferences
from quantis.ui.views.widgets.cover_art import load_track_cover, paint_rounded_cover
from quantis.ui.views.widgets.delegate_paint_kit import (
    FONT_AUTHOR,
    FONT_INDEX,
    FONT_TITLE,
    SOURCE_LABELS,
    paint_colors,
)


class PlaylistTrackDelegate(QStyledItemDelegate):
    ROW_HEIGHT = 56
    INDEX_WIDTH = 36
    COVER_SIZE = 40

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fm_title = QFontMetrics(FONT_TITLE)
        self._fm_author = QFontMetrics(FONT_AUTHOR)
        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self._on_theme_changed)

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
        return load_track_cover(track, self.COVER_SIZE)

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
        if is_playing:
            painter.fillRect(rect, colors.bg_playing)
        elif hovered or selected:
            painter.fillRect(rect, colors.bg_hover)
        elif row % 2 == 1:
            painter.fillRect(rect, colors.bg_alt)

        if is_playing:
            painter.fillRect(
                QRect(rect.left(), rect.top() + 8, 3, rect.height() - 16),
                colors.accent,
            )

        inner = rect.adjusted(8, 0, -8, 0)
        idx_rect = QRect(inner.left(), inner.top(), self.INDEX_WIDTH, inner.height())
        cover_rect = QRect(
            idx_rect.right() + 10,
            inner.top() + (inner.height() - self.COVER_SIZE) // 2,
            self.COVER_SIZE,
            self.COVER_SIZE,
        )
        text_left = cover_rect.right() + 12
        text_w = max(0, inner.right() - text_left)

        painter.setFont(FONT_INDEX)
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

        painter.setFont(FONT_TITLE)
        painter.setPen(colors.title_playing if is_playing else colors.title)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._fm_title.elidedText(
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

        painter.setFont(FONT_AUTHOR)
        painter.setPen(colors.subtitle)
        painter.drawText(
            author_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._fm_author.elidedText(subtitle, Qt.TextElideMode.ElideRight, text_w),
        )
        painter.restore()
