from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QRect, QSize, Qt
from PySide6.QtGui import (
    QColor,
    QFontMetrics,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from quantis.models import Track
from quantis.ui.models import TrackListModel
from quantis.ui.preferences import UiPreferences
from quantis.ui.views.widgets.cover_art import load_track_cover, paint_rounded_cover
from quantis.ui.views.widgets.delegate_paint_kit import (
    C_TITLE_PLAYING,
    FONT_ACTION,
    FONT_AUTHOR,
    FONT_COVER,
    FONT_EDITORIAL_AUTHOR,
    FONT_EDITORIAL_INDEX,
    FONT_EDITORIAL_TITLE,
    FONT_TITLE,
    SOURCE_LABELS,
    paint_colors,
)


class TrackCardDelegate(QStyledItemDelegate):
    CARD_HEIGHT = 56
    CARD_RADIUS = 10
    COVER_SIZE = 40
    ACTION_SIZE = 26

    _C_DL_OK_BG = QColor(34, 197, 94, 60)
    _C_DL_OK_PEN = QColor(34, 197, 94, 140)
    _C_EDITORIAL_BG = QColor(12, 12, 14)
    _C_EDITORIAL_HOVER = QColor(255, 255, 255, 8)
    _C_EDITORIAL_IDX = QColor(255, 255, 255, 10)
    _C_EDITORIAL_AUTHOR = QColor(242, 240, 235, 100)
    _C_EDITORIAL_TITLE = QColor(242, 240, 235)

    def __init__(
        self,
        parent=None,
        on_download: Callable[[int], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_download = on_download
        self._prefs = UiPreferences()
        self._editorial = self._prefs.theme.card_style == "editorial"
        self._prefs.theme_changed.connect(self._on_theme_changed)
        self._fm_title = QFontMetrics(FONT_TITLE)
        self._fm_author = QFontMetrics(FONT_AUTHOR)
        self._fm_editorial_title = QFontMetrics(FONT_EDITORIAL_TITLE)
        self._fm_editorial_author = QFontMetrics(FONT_EDITORIAL_AUTHOR)

    def _on_theme_changed(self) -> None:
        self._editorial = self._prefs.theme.card_style == "editorial"
        parent = self.parent()
        if parent is not None and hasattr(parent, "viewport"):
            parent.viewport().update()
        elif parent is not None:
            parent.update()

    def sizeHint(self, option, index) -> QSize:
        view = option.widget
        width = 320
        if view is not None:
            if hasattr(view, "viewport"):
                width = max(view.viewport().width(), width)
            else:
                width = max(view.width(), width)
        return QSize(width, self.CARD_HEIGHT)

    def _action_rect(self, rect: QRect) -> QRect:
        inner = rect.adjusted(4, 2, -8, -2)
        return QRect(
            inner.right() - self.ACTION_SIZE,
            inner.center().y() - self.ACTION_SIZE // 2,
            self.ACTION_SIZE,
            self.ACTION_SIZE,
        )

    def editorEvent(self, event, model, option, index):
        if (
            self._on_download is not None
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            track: Track | None = index.data(TrackListModel.TrackRole)
            if track is not None and not track.downloaded:
                if self._action_rect(option.rect).contains(event.pos()):
                    self._on_download(index.row())
                    return True
        return super().editorEvent(event, model, option, index)

    def paint(self, painter: QPainter, option, index) -> None:
        track: Track | None = index.data(TrackListModel.TrackRole)
        if track is None:
            return

        is_playing = bool(index.data(TrackListModel.IsPlayingRole))
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect.adjusted(4, 2, -4, -2)

        if self._editorial:
            self._paint_editorial(
                painter, rect, track, index.row(), is_playing, hovered, selected
            )
        else:
            self._paint_default(painter, rect, track, is_playing, hovered, selected)

        if self._on_download is None:
            return

        action_rect = self._action_rect(option.rect)
        if track.downloaded:
            painter.setBrush(self._C_DL_OK_BG)
            painter.setPen(QPen(self._C_DL_OK_PEN, 1))
            painter.drawEllipse(action_rect)
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(FONT_ACTION)
            painter.drawText(action_rect, Qt.AlignmentFlag.AlignCenter, "✓")
        elif hovered:
            colors = paint_colors(self._prefs.ui_theme)
            painter.setBrush(colors.dl_hover_bg)
            painter.setPen(QPen(colors.dl_hover_pen, 1))
            painter.drawEllipse(action_rect)
            painter.setPen(colors.dl_hover_text)
            painter.setFont(FONT_ACTION)
            painter.drawText(action_rect, Qt.AlignmentFlag.AlignCenter, "↓")

    def _paint_default(
        self,
        painter: QPainter,
        rect: QRect,
        track: Track,
        is_playing: bool,
        hovered: bool,
        selected: bool,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        colors = paint_colors(self._prefs.ui_theme)

        if is_playing:
            painter.setBrush(colors.bg_playing)
        elif hovered or selected:
            painter.setBrush(colors.bg_hover)
        else:
            painter.setBrush(colors.bg_idle)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, self.CARD_RADIUS, self.CARD_RADIUS)

        if is_playing:
            bar = QRect(rect.left() + 2, rect.top() + 10, 3, rect.height() - 20)
            painter.setBrush(colors.accent)
            painter.drawRoundedRect(bar, 2, 2)

        cover_rect = QRect(
            rect.left() + 12,
            rect.top() + (rect.height() - self.COVER_SIZE) // 2,
            self.COVER_SIZE,
            self.COVER_SIZE,
        )
        cover = load_track_cover(track, self.COVER_SIZE)
        paint_rounded_cover(
            painter,
            cover_rect,
            label=track.title or "?",
            pixmap=cover,
            source_key=str(track.source),
            radius=8,
        )

        if hovered and not is_playing:
            overlay = QPainterPath()
            overlay.addRoundedRect(cover_rect, 8, 8)
            painter.fillPath(overlay, QColor(0, 0, 0, 118))
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(FONT_COVER)
            painter.drawText(cover_rect, Qt.AlignmentFlag.AlignCenter, "▶")

        action_w = self.ACTION_SIZE + 16 if self._on_download else 8
        text_left = cover_rect.right() + 12
        text_right = rect.right() - action_w
        text_w = max(0, text_right - text_left)
        title_rect = QRect(text_left, rect.top() + 10, text_w, 20)
        author_rect = QRect(text_left, rect.top() + 28, text_w, 16)

        painter.setPen(colors.title_playing if is_playing else colors.title)
        painter.setFont(FONT_TITLE)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._fm_title.elidedText(track.title, Qt.TextElideMode.ElideRight, text_w),
        )

        source_key = str(track.source).lower()
        badge = SOURCE_LABELS.get(source_key, "")
        subtitle = track.author or ""
        if badge:
            subtitle = f"{subtitle} · {badge}" if subtitle else badge

        painter.setPen(colors.subtitle)
        painter.setFont(FONT_AUTHOR)
        painter.drawText(
            author_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._fm_author.elidedText(subtitle, Qt.TextElideMode.ElideRight, text_w),
        )

    def _paint_editorial(
        self,
        painter: QPainter,
        rect: QRect,
        track: Track,
        row: int,
        is_playing: bool,
        hovered: bool,
        selected: bool,
    ) -> None:
        inner = rect.adjusted(1, 1, -1, -1)
        painter.fillRect(inner, self._C_EDITORIAL_BG)

        if is_playing:
            glow = QLinearGradient(inner.topLeft(), inner.bottomRight())
            glow.setColorAt(0.0, QColor(0, 229, 255, 20))
            glow.setColorAt(0.5, QColor(230, 59, 46, 16))
            glow.setColorAt(1.0, QColor(255, 42, 127, 8))
            painter.fillRect(inner, glow)
        elif hovered or selected:
            painter.fillRect(inner, self._C_EDITORIAL_HOVER)

        if is_playing:
            painter.fillRect(
                inner.left(),
                inner.top() + 8,
                3,
                inner.height() - 16,
                QColor(0, 229, 255, 220),
            )
            painter.fillRect(
                inner.left() + 3,
                inner.top() + 8,
                2,
                inner.height() - 16,
                QColor(230, 59, 46, 200),
            )

        painter.setFont(FONT_EDITORIAL_INDEX)
        painter.setPen(self._C_EDITORIAL_IDX)
        painter.drawText(
            inner.adjusted(0, 0, -12, 0),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            f"{row + 1:02d}",
        )

        action_w = self.ACTION_SIZE + 16 if self._on_download else 8
        text_left = inner.left() + 16
        text_right = inner.right() - action_w
        text_w = max(0, text_right - text_left)
        title_rect = QRect(text_left, inner.top() + 10, text_w, 22)
        author_rect = QRect(text_left, inner.top() + 30, text_w, 16)

        painter.setPen(C_TITLE_PLAYING if is_playing else self._C_EDITORIAL_TITLE)
        painter.setFont(FONT_EDITORIAL_TITLE)
        painter.drawText(
            title_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._fm_editorial_title.elidedText(
                track.title, Qt.TextElideMode.ElideRight, text_w
            ),
        )

        painter.setFont(FONT_EDITORIAL_AUTHOR)
        painter.setPen(self._C_EDITORIAL_AUTHOR)
        painter.drawText(
            author_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            self._fm_editorial_author.elidedText(
                track.author.upper(), Qt.TextElideMode.ElideRight, text_w
            ),
        )
