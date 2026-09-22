"""Единый 16px бейдж источника на обложке."""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from quantis.models import TrackSource
from quantis.ui.design_tokens import (
    BADGE_SOUNDCLOUD,
    BADGE_YANDEX,
    BADGE_YOUTUBE,
    SURFACE,
)

BADGE_SIZE = 16
_BORDER = QColor(SURFACE)
_YT = QColor(BADGE_YOUTUBE)
_YA = QColor(BADGE_YANDEX)
_SC = QColor(BADGE_SOUNDCLOUD)
_FONT = QFont("Bahnschrift", 6, QFont.Weight.Bold)


def source_badge_color(source: str | None) -> QColor:
    key = str(source or "").lower()
    if key == TrackSource.YOUTUBE or key == "youtube":
        return _YT
    if key == TrackSource.YANDEX or key == "yandex":
        return _YA
    if key == TrackSource.SOUNDCLOUD or key == "soundcloud":
        return _SC
    return QColor(140, 150, 170)


def source_badge_letter(source: str | None) -> str:
    key = str(source or "").lower()
    if key in (TrackSource.YOUTUBE, "youtube"):
        return "Y"
    if key in (TrackSource.YANDEX, "yandex"):
        return "Я"
    if key in (TrackSource.SOUNDCLOUD, "soundcloud"):
        return "S"
    return "?"


def paint_source_badge(
    painter: QPainter,
    cover_rect: QRect,
    source: str | None,
    *,
    size: int = BADGE_SIZE,
    border_color: QColor | None = None,
) -> QRect:
    """Рисует кружок в правом нижнем углу обложки. Возвращает rect бейджа."""
    badge = QRect(
        cover_rect.right() - size + 2,
        cover_rect.bottom() - size + 2,
        size,
        size,
    )
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(source_badge_color(source))
    painter.setPen(QPen(border_color or _BORDER, 2))
    painter.drawEllipse(badge)

    painter.setPen(
        QColor(20, 22, 28)
        if source_badge_letter(source) == "Я"
        else QColor(255, 255, 255)
    )
    painter.setFont(_FONT)
    painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, source_badge_letter(source))
    painter.restore()
    return badge
