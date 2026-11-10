"""Карточка с обложкой для плейлистов и миксов, с эффектом при наведении.

При наведении карточка приподнимается, обложка чуть приближается, вокруг
загорается градиентная рамка цвета акцента, снизу появляется кнопка ▶.
Клик по ▶ — играть сразу, по остальной карточке — открыть.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import (
    QEasingCurve,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QEnterEvent,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from quantis.ui.corners import corner
from quantis.ui.fonts import app_font
from quantis.ui.views.widgets.cover_art import (
    CoverDecoder,
    CoverEvents,
    gradient_for_name,
)
from quantis.ui.views.widgets.delegate_paint_kit import paint_colors

CoverSource = Callable[[int], Sequence[QPixmap | None]]
"""По размеру в px — одна обложка или до четырёх для коллажа."""

_HOVER_MS = 200
_LIFT = 4.0
_ZOOM = 0.06
_GLOW = 6


def _with_alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlphaF(max(0.0, min(1.0, alpha)))
    return out


def _partner(accent: QColor) -> QColor:
    """Второй цвет рамки: акцент со сдвигом оттенка к розовому."""
    hue = accent.hsvHueF()
    if hue < 0:
        return QColor(236, 72, 153)
    shifted = (hue + 0.12) % 1.0
    return QColor.fromHsvF(
        shifted, min(1.0, accent.hsvSaturationF() + 0.1), accent.valueF()
    )


class ArtCard(QWidget):
    """Квадрат обложки, под ним название и подпись."""

    TITLE_H = 20
    META_H = 16
    GAP = 8
    PAD = _GLOW
    CAPTION_H = GAP + TITLE_H + META_H
    ROW_EXTRA = CAPTION_H - PAD + 2
    """Высота карточки = ширина + ROW_EXTRA (обложка уже ширины на 2·PAD)."""

    activated = Signal(object)
    play_requested = Signal(object)

    def __init__(
        self,
        item: object,
        *,
        title: str,
        subtitle: str = "",
        covers: CoverSource,
        kicker: str = "",
        title_on_cover: bool = False,
        icon_cover: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._item = item
        self._title = title
        self._subtitle = subtitle
        self._covers = covers
        self._kicker = kicker
        self._title_on_cover = title_on_cover
        self._icon_cover = icon_cover
        self._hover = 0.0
        self._pressed_play = False
        self.setObjectName("artCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(_HOVER_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        CoverDecoder.instance().ready.connect(self.update)
        # Слоты-методы, а не lambda: Qt сам отключит их, когда карточку удалят.
        CoverEvents.instance().cover_ready.connect(self._on_cover_file)

    def _on_cover_file(self, _path: str) -> None:
        self.update()

    # --- данные ----------------------------------------------------------

    @property
    def item(self) -> object:
        return self._item

    @property
    def hover_progress(self) -> float:
        return self._hover

    def apply_cell(self, width: int, height: int) -> None:
        self.setFixedSize(width, height)
        self.update()

    def cover_rect(self) -> QRectF:
        side = max(16.0, float(self.width() - self.PAD * 2))
        return QRectF(self.PAD, self.PAD, side, side)

    def play_rect(self) -> QRectF:
        cover = self.cover_rect()
        size = max(30.0, min(46.0, cover.width() * 0.26))
        margin = max(8.0, cover.width() * 0.06)
        return QRectF(
            cover.right() - margin - size,
            cover.bottom() - margin - size,
            size,
            size,
        )

    # --- наведение -------------------------------------------------------

    def _on_anim(self, value: object) -> None:
        self._hover = float(value)  # type: ignore[arg-type]
        self.update()

    def _animate_to(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event: QEnterEvent) -> None:
        self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event: object) -> None:
        self._animate_to(0.0)
        super().leaveEvent(event)  # type: ignore[arg-type]

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._pressed_play = self.play_rect().contains(event.position())
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            if self._pressed_play and self.play_rect().contains(event.position()):
                self.play_requested.emit(self._item)
            else:
                self.activated.emit(self._item)
        self._pressed_play = False
        super().mouseReleaseEvent(event)

    # --- рисование -------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        colors = paint_colors()
        t = self._hover
        lift = _LIFT * t
        base = self.cover_rect()
        cover = base.translated(0, -lift)
        radius = corner(16)

        if t > 0.01:
            self._paint_glow(painter, cover, radius, colors.accent, t)
        self._paint_cover(painter, cover, radius, t)
        if t > 0.01:
            self._paint_play(painter, cover, t, colors.accent)

        text_top = base.bottom() + self.GAP
        width = int(base.width())
        if self._title_on_cover:
            # Название уже крупно на обложке — под ней только подпись.
            meta_font = app_font(11, QFont.Weight.Medium)
            painter.setFont(meta_font)
            painter.setPen(colors.title_playing if t > 0.5 else colors.subtitle)
            painter.drawText(
                QRect(int(base.left()), int(text_top), width, self.TITLE_H),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(meta_font).elidedText(
                    self._subtitle, Qt.TextElideMode.ElideRight, width
                ),
            )
            painter.end()
            return
        painter.setPen(colors.title_playing if t > 0.5 else colors.title)
        title_font = app_font(12, QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.drawText(
            QRect(int(base.left()), int(text_top), width, self.TITLE_H),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(title_font).elidedText(
                self._title, Qt.TextElideMode.ElideRight, width
            ),
        )
        if self._subtitle:
            meta_font = app_font(10)
            painter.setFont(meta_font)
            painter.setPen(colors.subtitle)
            painter.drawText(
                QRect(
                    int(base.left()), int(text_top) + self.TITLE_H, width, self.META_H
                ),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(meta_font).elidedText(
                    self._subtitle, Qt.TextElideMode.ElideRight, width
                ),
            )
        painter.end()

    def _paint_glow(
        self,
        painter: QPainter,
        cover: QRectF,
        radius: float,
        accent: QColor,
        t: float,
    ) -> None:
        partner = _partner(accent)
        # Мягкое свечение — несколько расходящихся контуров, затем чёткая рамка.
        for step, alpha in ((5.0, 0.10), (3.5, 0.18), (2.0, 0.30)):
            grow = step
            rect = cover.adjusted(-grow, -grow, grow, grow)
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            gradient.setColorAt(0.0, _with_alpha(accent, alpha * t))
            gradient.setColorAt(1.0, _with_alpha(partner, alpha * t))
            pen = QPen(gradient, 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect, radius + grow, radius + grow)
        edge = cover.adjusted(-0.75, -0.75, 0.75, 0.75)
        gradient = QLinearGradient(edge.topLeft(), edge.bottomRight())
        gradient.setColorAt(0.0, _with_alpha(accent, 0.95 * t))
        gradient.setColorAt(1.0, _with_alpha(partner, 0.95 * t))
        painter.setPen(QPen(gradient, 1.6))
        painter.drawRoundedRect(edge, radius + 0.75, radius + 0.75)

    def _paint_cover(
        self, painter: QPainter, cover: QRectF, radius: float, t: float
    ) -> None:
        painter.save()
        clip = QPainterPath()
        clip.addRoundedRect(cover, radius, radius)
        painter.setClipPath(clip)
        side = int(cover.width())
        pixmaps = [p for p in self._covers(side) if p is not None and not p.isNull()]
        zoom = 1.0 + _ZOOM * t
        target = QRectF(
            cover.center().x() - cover.width() * zoom / 2,
            cover.center().y() - cover.height() * zoom / 2,
            cover.width() * zoom,
            cover.height() * zoom,
        )
        if self._icon_cover and pixmaps:
            painter.fillPath(clip, QColor(255, 255, 255, 14))
            inset = cover.width() * 0.2
            painter.drawPixmap(
                target.adjusted(inset, inset, -inset, -inset).toRect(), pixmaps[0]
            )
        elif len(pixmaps) >= 4:
            half_w = target.width() / 2
            half_h = target.height() / 2
            for index, pixmap in enumerate(pixmaps[:4]):
                cell = QRectF(
                    target.left() + (index % 2) * half_w,
                    target.top() + (index // 2) * half_h,
                    half_w,
                    half_h,
                )
                painter.drawPixmap(cell.toRect(), pixmap)
        elif pixmaps:
            painter.drawPixmap(target.toRect(), pixmaps[0])
        else:
            start, end = gradient_for_name(self._title or "?")
            gradient = QLinearGradient(target.topLeft(), target.bottomRight())
            gradient.setColorAt(0.0, start)
            gradient.setColorAt(1.0, end)
            painter.fillRect(target, gradient)
            if not self._title_on_cover:
                painter.setPen(QColor(255, 255, 255, 230))
                painter.setFont(app_font(max(9, side // 4), QFont.Weight.Bold))
                painter.drawText(
                    cover,
                    Qt.AlignmentFlag.AlignCenter,
                    (self._title[:1] or "?").upper(),
                )

        if self._title_on_cover:
            self._paint_cover_title(painter, cover)
        if t > 0.01:
            shade = QLinearGradient(cover.topLeft(), cover.bottomLeft())
            shade.setColorAt(0.45, QColor(0, 0, 0, 0))
            shade.setColorAt(1.0, QColor(0, 0, 0, int(130 * t)))
            painter.fillRect(cover, shade)
        painter.restore()

    def _paint_cover_title(self, painter: QPainter, cover: QRectF) -> None:
        shade = QLinearGradient(cover.topLeft(), cover.bottomLeft())
        shade.setColorAt(0.35, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 175))
        painter.fillRect(cover, shade)
        margin = max(10, int(cover.width() * 0.08))
        if self._kicker:
            kicker_font = app_font(8, QFont.Weight.Bold)
            painter.setFont(kicker_font)
            metrics = QFontMetrics(kicker_font)
            pill = QRectF(
                cover.left() + margin,
                cover.top() + margin,
                metrics.horizontalAdvance(self._kicker) + 14,
                metrics.height() + 6,
            )
            path = QPainterPath()
            path.addRoundedRect(pill, pill.height() / 2, pill.height() / 2)
            painter.fillPath(path, QColor(0, 0, 0, 120))
            painter.setPen(QColor(255, 255, 255, 230))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, self._kicker)
        size = max(12, int(cover.width() * 0.12))
        font = app_font(size, QFont.Weight.Black)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        # Справа внизу появляется ▶ — текст до неё не доходит.
        play_room = self.play_rect().width() + 6
        box = QRectF(
            cover.left() + margin,
            cover.top() + cover.height() * 0.40,
            cover.width() - margin * 2 - play_room,
            cover.height() * 0.60 - margin,
        )
        metrics = QFontMetrics(font)
        while size > 11 and any(
            metrics.horizontalAdvance(word) > box.width()
            for word in self._title.split()
        ):
            size -= 1
            font = app_font(size, QFont.Weight.Black)
            metrics = QFontMetrics(font)
        painter.setFont(font)
        painter.drawText(
            box,
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignBottom
            | Qt.TextFlag.TextWordWrap,
            self._title,
        )

    def _paint_play(
        self, painter: QPainter, cover: QRectF, t: float, accent: QColor
    ) -> None:
        rect = self.play_rect().translated(0, -_LIFT * t + (1 - t) * 8)
        scale = 0.7 + 0.3 * t
        center = rect.center()
        radius = rect.width() / 2 * scale
        painter.save()
        painter.setOpacity(t)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawEllipse(center + QPointF(0, 2), radius, radius)
        painter.setBrush(accent)
        painter.drawEllipse(center, radius, radius)
        tri = radius * 0.42
        painter.setBrush(QColor(255, 255, 255))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(center.x() - tri * 0.7, center.y() - tri),
                    QPointF(center.x() - tri * 0.7, center.y() + tri),
                    QPointF(center.x() + tri, center.y()),
                ]
            )
        )
        painter.restore()
