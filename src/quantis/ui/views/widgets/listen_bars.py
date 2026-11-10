"""Горизонтальные бары топа: обложка, название, подпись и полоса значения."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QSizePolicy, QWidget

from quantis.models import Track
from quantis.ui.corners import corner
from quantis.ui.design_tokens import ACCENT_FALLBACK
from quantis.ui.fonts import app_font
from quantis.ui.preferences import UiPreferences
from quantis.ui.views.widgets.cover_art import (
    CoverDecoder,
    CoverEvents,
    paint_rounded_cover,
    request_track_cover,
)
from quantis.ui.views.widgets.delegate_paint_kit import paint_colors

_ROW_H = 54
_PAD = 4
_COVER = 40


@dataclass(frozen=True)
class RankRow:
    title: str
    subtitle: str
    value: int
    value_text: str = ""
    cover_track: Track | None = None
    round_cover: bool = False
    """Круглая обложка — у артистов, как фото профиля."""


def track_rows(tracks: list[Track]) -> list[RankRow]:
    return [
        RankRow(
            title=t.title or "Без названия",
            subtitle=t.author or "",
            value=max(0, t.listen_count),
            cover_track=t,
        )
        for t in tracks
    ]


class ListenBars(QWidget):
    track_activated = Signal(int)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        empty_text: str = "Пока нет завершённых прослушиваний",
        clickable: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("listenBars")
        self._clickable = clickable
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._rows: list[RankRow] = []
        self._empty_text = empty_text
        self._hover = -1
        self._accent = QColor(ACCENT_FALLBACK)
        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self.update)
        CoverDecoder.instance().ready.connect(self.update)
        CoverEvents.instance().cover_ready.connect(self._on_cover_file)
        self.setMouseTracking(True)
        self._sync_height()

    def _on_cover_file(self, _path: str) -> None:
        self.update()

    def set_accent(self, color: QColor) -> None:
        if color.isValid():
            self._accent = QColor(color)
            self.update()

    def set_tracks(self, tracks: list[Track]) -> None:
        self.set_rows(track_rows(tracks))

    def set_rows(self, rows: list[RankRow]) -> None:
        self._rows = list(rows)
        self._hover = -1
        self._sync_height()
        self.update()

    def _sync_height(self) -> None:
        rows = max(1, len(self._rows))
        self.setFixedHeight(rows * _ROW_H + _PAD * 2)

    def _index_at(self, y: int) -> int:
        if not self._rows:
            return -1
        row = (y - _PAD) // _ROW_H
        if 0 <= row < len(self._rows):
            return int(row)
        return -1

    def mouseMoveEvent(self, event) -> None:
        index = self._index_at(int(event.position().y()))
        if index != self._hover:
            self._hover = index
            self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._hover != -1:
            self._hover = -1
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._clickable and event.button() == Qt.MouseButton.LeftButton:
            index = self._index_at(int(event.position().y()))
            if index >= 0:
                self.track_activated.emit(index)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        colors = paint_colors(self._prefs.theme)
        if not self._rows:
            painter.setPen(colors.empty)
            painter.setFont(QFont(self.font().family(), 12))
            painter.drawText(
                self.rect().adjusted(12, 0, -12, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                self._empty_text,
            )
            painter.end()
            return

        peak = max((row.value for row in self._rows), default=1) or 1
        title_font = app_font(12, QFont.Weight.DemiBold)
        meta_font = app_font(10)
        index_font = app_font(11, QFont.Weight.Bold)
        count_font = app_font(12, QFont.Weight.Bold)

        width = self.width()
        cover_left = 40
        text_left = cover_left + _COVER + 12
        bar_right = width - 72
        bar_span = max(40, bar_right - text_left)

        for index, item in enumerate(self._rows):
            y = _PAD + index * _ROW_H
            row = QRect(8, y + 2, width - 16, _ROW_H - 4)
            if index == self._hover:
                hover = QPainterPath()
                hover.addRoundedRect(QRectF(row), corner(12), corner(12))
                painter.fillPath(hover, colors.bg_hover)

            # Первые три места — цветом акцента, как пьедестал.
            painter.setPen(self._accent if index < 3 else colors.meta)
            painter.setFont(index_font)
            painter.drawText(
                QRect(12, y, 24, _ROW_H),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignCenter,
                str(index + 1),
            )

            cover_rect = QRect(cover_left, y + (_ROW_H - _COVER) // 2, _COVER, _COVER)
            pixmap = (
                request_track_cover(item.cover_track, _COVER)
                if item.cover_track is not None
                else None
            )
            if item.round_cover:
                painter.save()
                clip = QPainterPath()
                clip.addEllipse(QRectF(cover_rect))
                painter.setClipPath(clip)
                paint_rounded_cover(
                    painter,
                    cover_rect,
                    label=item.title,
                    pixmap=pixmap,
                    radius=_COVER // 2,
                    with_badge=False,
                )
                painter.restore()
            else:
                paint_rounded_cover(
                    painter,
                    cover_rect,
                    label=item.title,
                    pixmap=pixmap,
                    radius=8,
                    with_badge=False,
                )

            painter.setPen(colors.title)
            painter.setFont(title_font)
            painter.drawText(
                QRect(text_left, y + 6, bar_span, 20),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                painter.fontMetrics().elidedText(
                    item.title, Qt.TextElideMode.ElideRight, bar_span
                ),
            )
            if item.subtitle:
                painter.setPen(colors.subtitle)
                painter.setFont(meta_font)
                painter.drawText(
                    QRect(text_left, y + 24, bar_span, 14),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    painter.fontMetrics().elidedText(
                        item.subtitle, Qt.TextElideMode.ElideRight, bar_span
                    ),
                )

            ratio = max(0.04, min(1.0, item.value / peak))
            track_rect = QRectF(text_left, y + 41, bar_span, 4)
            groove = QPainterPath()
            groove.addRoundedRect(track_rect, 2, 2)
            painter.fillPath(groove, colors.bg_hover)
            bar_rect = QRectF(text_left, y + 41, bar_span * ratio, 4)
            path = QPainterPath()
            path.addRoundedRect(bar_rect, 2, 2)
            gradient = QLinearGradient(bar_rect.topLeft(), bar_rect.topRight())
            accent = self._accent
            gradient.setColorAt(
                0.0, QColor(accent.red(), accent.green(), accent.blue(), 235)
            )
            gradient.setColorAt(
                1.0, QColor(accent.red(), accent.green(), accent.blue(), 110)
            )
            painter.fillPath(path, gradient)

            painter.setPen(colors.title)
            painter.setFont(count_font)
            painter.drawText(
                QRect(bar_right + 8, y, 56, _ROW_H),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                item.value_text or str(item.value),
            )
        painter.end()
