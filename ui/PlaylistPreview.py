import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QSizePolicy, QGraphicsDropShadowEffect,
)
from PySide6.QtGui import (
    QPixmap, QColor, QPainter, QPen, QLinearGradient, QBrush, QFont, QPainterPath,
)
from PySide6.QtCore import Qt, Signal, QTimeLine, QRectF

from providers import PathProvider
from utils import get_ru_words_for_number

_CARD_W = 170
_CARD_H = 220
_COVER_SIZE = 140
_COVER_RADIUS = 12
_CARD_RADIUS = 14
_ANIM_MS = 180
_HOVER_LIFT = 6  # px shadow offset change


class PlaylistPreview(QWidget):
    """Карточка плейлиста для главной страницы."""

    clicked = Signal(object)

    def __init__(self, playlist, parent=None):
        super().__init__(parent)

        self._path = PathProvider()
        self._playlist = playlist
        self._hovered = False
        self._hover_t = 0.0  # 0..1

        self.setFixedSize(_CARD_W, _CARD_H)
        self.setCursor(Qt.PointingHandCursor)

        # ── layout ──
        lay = QVBoxLayout(self)
        lay.setContentsMargins((_CARD_W - _COVER_SIZE) // 2, 12, (_CARD_W - _COVER_SIZE) // 2, 10)
        lay.setSpacing(8)

        # ── cover ──
        self._cover_label = QLabel()
        self._cover_label.setFixedSize(_COVER_SIZE, _COVER_SIZE)
        self._cover_label.setAlignment(Qt.AlignCenter)
        self._cover_label.setStyleSheet(f"border-radius: {_COVER_RADIUS}px; background: transparent;")
        self._cover_pixmap: QPixmap | None = None
        self._load_cover()
        lay.addWidget(self._cover_label, alignment=Qt.AlignCenter)

        # ── title ──
        self._title = QLabel(playlist.name if playlist else "—")
        self._title.setAlignment(Qt.AlignLeft)
        self._title.setWordWrap(False)
        self._title.setStyleSheet(
            "color: #fff; font-size: 13px; font-weight: 600; background: transparent;"
        )
        lay.addWidget(self._title)

        # ── count ──
        count = len(playlist.tracks.values) if playlist else 0
        self._count = QLabel(get_ru_words_for_number(count))
        self._count.setAlignment(Qt.AlignLeft)
        self._count.setStyleSheet(
            "color: rgba(255,255,255,90); font-size: 11px; background: transparent;"
        )
        lay.addWidget(self._count)

        lay.addStretch()

        # ── shadow ──
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(12)
        self._shadow.setOffset(0, 4)
        self._shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(self._shadow)

        # ── hover animation ──
        self._tl = QTimeLine(_ANIM_MS, self)
        self._tl.setUpdateInterval(16)
        self._tl.valueChanged.connect(self._anim_tick)
        self._anim_from = 0.0
        self._anim_to = 0.0

    # ── cover loading ──

    def _load_cover(self) -> None:
        """Try to load cover from disk. Falls back to a nice gradient placeholder."""
        cover_path = self._resolve_cover()
        if cover_path and os.path.isfile(cover_path):
            pm = QPixmap(cover_path)
            if not pm.isNull():
                self._cover_pixmap = pm.scaled(
                    _COVER_SIZE, _COVER_SIZE,
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
                )
        # if still None — paintEvent will draw placeholder

    def _resolve_cover(self) -> str | None:
        pl = self._playlist
        if not pl:
            return None
        if pl.cover_path and os.path.isfile(pl.cover_path):
            return pl.cover_path
        # try first track's cover
        tracks = pl.tracks.values
        if tracks:
            path = self._path.get_cover_path(tracks[0])
            if os.path.isfile(path):
                pl.cover_path = path
                return path
        return None

    def set_cover_pixmap(self, pm: QPixmap) -> None:
        """Called externally after async cover download."""
        self._cover_pixmap = pm.scaled(
            _COVER_SIZE, _COVER_SIZE,
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
        )
        self.update()

    # ── painting ──

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(0, 0, self.width(), self.height())

        # card background
        bg_alpha = 18 + int(12 * self._hover_t)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, bg_alpha))
        p.drawRoundedRect(rect, _CARD_RADIUS, _CARD_RADIUS)

        # cover area
        cx = (self.width() - _COVER_SIZE) / 2
        cy = 12.0
        cover_rect = QRectF(cx, cy, _COVER_SIZE, _COVER_SIZE)

        # clip cover to rounded rect
        cover_clip = QPainterPath()
        cover_clip.addRoundedRect(cover_rect, _COVER_RADIUS, _COVER_RADIUS)
        p.setClipPath(cover_clip)

        if self._cover_pixmap and not self._cover_pixmap.isNull():
            p.drawPixmap(int(cx), int(cy), self._cover_pixmap)
        else:
            # placeholder gradient
            grad = QLinearGradient(cover_rect.topLeft(), cover_rect.bottomRight())
            grad.setColorAt(0.0, QColor(30, 40, 60))
            grad.setColorAt(0.5, QColor(40, 50, 80))
            grad.setColorAt(1.0, QColor(20, 30, 50))
            p.setBrush(QBrush(grad))
            p.drawRect(cover_rect)

            # music note icon
            p.setPen(QColor(255, 255, 255, 60))
            font = QFont("Segoe UI", 36)
            p.setFont(font)
            p.drawText(cover_rect, Qt.AlignCenter, "♫")

        # subtle bottom gradient over cover (text readability)
        p.setClipPath(cover_clip)
        bottom_grad = QLinearGradient(
            cover_rect.bottomLeft().x(), cover_rect.bottom() - 40,
            cover_rect.bottomLeft().x(), cover_rect.bottom(),
        )
        bottom_grad.setColorAt(0.0, QColor(0, 0, 0, 0))
        bottom_grad.setColorAt(1.0, QColor(0, 0, 0, 60))
        p.setBrush(QBrush(bottom_grad))
        p.setPen(Qt.NoPen)
        p.drawRect(QRectF(cx, cover_rect.bottom() - 40, _COVER_SIZE, 40))

        p.setClipping(False)

        # hover border glow
        if self._hover_t > 0.01:
            glow_alpha = int(50 * self._hover_t)
            pen = QPen(QColor(0, 220, 255, glow_alpha), 1.5)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), _CARD_RADIUS, _CARD_RADIUS)

        p.end()
        super().paintEvent(event)

    # ── hover animation ──

    def _start_anim(self, target: float) -> None:
        self._tl.stop()
        self._anim_from = self._hover_t
        self._anim_to = target
        self._tl.start()

    def _anim_tick(self, progress: float) -> None:
        self._hover_t = self._anim_from + (self._anim_to - self._anim_from) * progress
        # shadow
        blur = 12 + int(14 * self._hover_t)
        y_off = 4 - int(_HOVER_LIFT * self._hover_t)
        self._shadow.setBlurRadius(blur)
        self._shadow.setOffset(0, y_off)
        self._shadow.setColor(QColor(0, 180, 255, int(40 * self._hover_t)))
        self.update()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._start_anim(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._start_anim(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._playlist:
            self.clicked.emit(self._playlist)
        super().mousePressEvent(event)
