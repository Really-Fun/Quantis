"""Мини-плеер: маленькое окно поверх остальных, пока главное свёрнуто.

Обложка, название, три кнопки и плавная волна, по которой бежит прогресс
трека. Фон — размытая обложка под затемнением, поэтому окно всегда тёмное и
от темы не зависит (таблица стилей главного окна сюда не доходит).

Волна — оформление, а не спектр звука: настоящих отсчётов у плеера нет. У
каждого трека она своя (зерно — ключ трека), на паузе затихает.
"""

from __future__ import annotations

import math
import random
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QToolButton, QWidget

from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.ui import resources
from quantis.ui.fonts import app_font
from quantis.ui.image_fx import blur_image, fill_crop
from quantis.ui.live_palette import LivePalette
from quantis.ui.viewmodels.player_vm import PlayerViewModel
from quantis.ui.views.widgets.cover_art import (
    CoverEvents,
    is_track_cover,
    load_cover_pixmap,
)
from quantis.ui.views.widgets.playlist_art import load_art

WIDTH, HEIGHT = 380, 180
RADIUS = 18
PAD = 16
COVER = 52
WAVE_TOP, BASELINE = 76, 114
"""Зона волны по вертикали: гребни растут вверх от линии прогресса."""
_FRAME_MS = 33
_POINTS = 48
_EXTRAPOLATE_MS = 3000
"""Насколько вперёд дотягиваем позицию между её обновлениями: в фоновом
режиме плеер сообщает её раз в 2 с, а точка на волне должна идти ровно."""

_QSS = """
QToolButton { background: transparent; border: none; border-radius: 17px; }
QToolButton:hover { background: rgba(255, 255, 255, 36); }
QToolButton:pressed { background: rgba(255, 255, 255, 60); }
QToolButton#miniPlay { background: #ffffff; border-radius: 21px; }
QToolButton#miniPlay:hover { background: rgba(255, 255, 255, 215); }
QToolTip { color: #ffffff; background: #16181d; border: 1px solid #2a2d35; }
"""


def wave_heights(seed: str, phase: float, level: float) -> list[float]:
    """Высоты гребней 0..1 в ``_POINTS`` точках: несколько волн разной длины
    бегут с разной скоростью, края прижаты к линии. ``level`` — громкость
    картинки (на паузе стремится к нулю)."""
    rnd = random.Random(seed)
    waves = [
        (rnd.uniform(1.5, 6.0), rnd.uniform(0.6, 1.9), rnd.uniform(0, math.tau))
        for _ in range(4)
    ]
    heights = []
    for i in range(_POINTS):
        x = i / (_POINTS - 1)
        value = 0.0
        for freq, speed, shift in waves:
            value += math.sin(x * freq * math.tau + phase * speed + shift)
        value = max(0.0, value / len(waves)) ** 1.6
        # tanh, а не обрезка: высокий гребень остаётся круглым, без «полки»
        heights.append(math.tanh(value * 2.4) * level * math.sin(x * math.pi))
    return heights


def _round_pen(brush) -> QPen:  # type: ignore[no-untyped-def]
    """Линия прогресса: 2 px со скруглёнными концами."""
    pen = QPen(brush, 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    return pen


def smooth_path(points: list[QPointF]) -> QPainterPath:
    """Плавная кривая через середины отрезков (без изломов в точках)."""
    path = QPainterPath(points[0])
    for prev, cur in zip(points, points[1:], strict=False):
        mid = QPointF((prev.x() + cur.x()) / 2, (prev.y() + cur.y()) / 2)
        path.quadTo(prev, mid)
    path.lineTo(points[-1])
    return path


class MiniPlayer(QWidget):
    restore_requested = Signal()
    """Вернуться в главное окно (кнопка, двойной щелчок, Esc, закрытие)."""

    def __init__(
        self,
        view_model: PlayerViewModel,
        path_provider: PathProvider,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vm = view_model
        self._paths = path_provider
        self.setWindowTitle("Quantis — мини-плеер")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(_QSS)

        self._track: Track | None = None
        self._thumb = QPixmap()
        self._backdrop = QImage()
        self._playing = False
        self._duration = 0
        self._position = 0
        self._position_at = monotonic()
        self._seek_to: int | None = None
        self._placed = False
        self._phase = 0.0
        self._level = 0.0
        self._palette = LivePalette.instance().current

        self._timer = QTimer(self)
        self._timer.setInterval(_FRAME_MS)
        self._timer.timeout.connect(self._tick)

        self._restore = self._button("maximize.svg", "Развернуть Quantis", 30, 14)
        self._restore.clicked.connect(self.restore_requested.emit)
        self._restore.move(WIDTH - PAD - 30 + 4, PAD - 4)
        self._prev = self._button("prev.svg", "Назад", 34, 16)
        self._prev.clicked.connect(self._vm.play_previous)
        self._play = self._button("play.svg", "Играть", 42, 18, dark=True)
        self._play.setObjectName("miniPlay")
        self._play.clicked.connect(self._vm.toggle_pause)
        self._next = self._button("next.svg", "Далее", 34, 16)
        self._next.clicked.connect(self._vm.play_next)
        center, y = WIDTH // 2, HEIGHT - 10 - 42
        self._play.move(center - 21, y)
        self._prev.move(center - 21 - 14 - 34, y + 4)
        self._next.move(center + 21 + 14, y + 4)

        self._vm.track_changed.connect(self._on_track)
        self._vm.is_playing_changed.connect(self._on_playing)
        self._vm.position_changed.connect(self._on_position)
        self._vm.duration_changed.connect(self._on_duration)
        LivePalette.instance().palette_changed.connect(self._on_palette)
        CoverEvents.instance().cover_ready.connect(self._on_cover_ready)

    def _button(
        self, icon: str, hint: str, size: int, icon_size: int, *, dark: bool = False
    ) -> QToolButton:
        button = QToolButton(self)
        color = QColor(12, 14, 18) if dark else QColor(255, 255, 255, 235)
        button.setIcon(resources.load_icon(icon, color))
        button.setIconSize(QSize(icon_size, icon_size))
        button.setFixedSize(size, size)
        button.setToolTip(hint)
        button.setAccessibleName(hint)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return button

    # ------------------------------------------------------------- состояние

    def sync(self) -> None:
        """Подтянуть текущий трек и состояние плеера (перед показом)."""
        self._vm.sync_from_player()

    def _on_track(self, track: Track) -> None:
        self._track = track
        self._position, self._position_at = 0, monotonic()
        self._load_cover()
        self.update()

    def _on_cover_ready(self, path: str) -> None:
        if self._track is not None and is_track_cover(self._track, path):
            self._load_cover()
            self.update()

    def _load_cover(self) -> None:
        self._thumb, self._backdrop = QPixmap(), QImage()
        if self._track is None:
            return
        path = Path(self._paths.get_cover_path(self._track))
        if not path.is_file():
            return
        self._thumb = load_cover_pixmap(path, COVER) or QPixmap()
        art = load_art(str(path))
        if not art.isNull():
            small = fill_crop(art, QSize(WIDTH // 2, HEIGHT // 2))
            self._backdrop = blur_image(small, 0.5)

    def _on_playing(self, playing: bool) -> None:
        self._position = self._shown_position()
        self._position_at = monotonic()
        self._playing = playing
        icon = "pause.svg" if playing else "play.svg"
        self._play.setIcon(resources.load_icon(icon, QColor(12, 14, 18)))
        hint = "Пауза" if playing else "Играть"
        self._play.setToolTip(hint)
        self._play.setAccessibleName(hint)
        self._sync_timer()

    def _on_position(self, position_ms: int) -> None:
        self._position, self._position_at = max(0, position_ms), monotonic()
        if not self._timer.isActive():
            self.update()

    def _on_duration(self, duration_ms: int) -> None:
        self._duration = max(0, duration_ms)
        self.update()

    def _on_palette(self, palette) -> None:  # type: ignore[no-untyped-def]
        self._palette = palette
        if self.isVisible():
            self.update()

    def _shown_position(self) -> int:
        """Позиция с дотяжкой по часам между обновлениями плеера."""
        if self._seek_to is not None:
            return self._seek_to
        position = self._position
        if self._playing:
            ahead = (monotonic() - self._position_at) * 1000
            position += int(min(ahead, _EXTRAPOLATE_MS))
        return min(position, self._duration) if self._duration > 0 else position

    # -------------------------------------------------------------- анимация

    def _sync_timer(self) -> None:
        """Кадры идут, пока окно видно и волна играет или ещё затихает."""
        moving = self._playing or self._level > 0.02
        if self.isVisible() and moving:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def _tick(self) -> None:
        target = 1.0 if self._playing else 0.0
        self._level += (target - self._level) * 0.12
        if self._playing or self._level > 0.02:
            self._phase += _FRAME_MS / 1000
        else:
            self._level = 0.0
            self._timer.stop()
        self.update()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        if not self._placed:
            self._placed = True
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                self.move(area.right() - WIDTH - 24, area.bottom() - HEIGHT - 24)
        self._sync_timer()

    def hideEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().hideEvent(event)
        self._timer.stop()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        # Закрыли мини-плеер средствами системы — это «вернуться в Quantis».
        super().closeEvent(event)
        self.restore_requested.emit()

    # ------------------------------------------------------------------ мышь

    def _wave_zone(self) -> QRectF:
        return QRectF(PAD, WAVE_TOP, WIDTH - 2 * PAD, BASELINE - WAVE_TOP + 10)

    def _seek_value(self, x: float) -> int:
        zone = self._wave_zone()
        share = (x - zone.left()) / max(1.0, zone.width())
        return int(max(0.0, min(1.0, share)) * self._duration)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._duration > 0 and self._wave_zone().contains(event.position()):
            self._seek_to = self._seek_value(event.position().x())
            self.update()
            return
        handle = self.windowHandle()
        if handle is not None:
            handle.startSystemMove()  # окно без рамки таскают за любое место

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._seek_to is not None:
            self._seek_to = self._seek_value(event.position().x())
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._seek_to is None:
            return
        target, self._seek_to = self._seek_to, None
        self._position, self._position_at = target, monotonic()
        self._vm.seek(target)
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._wave_zone().contains(event.position()):
            self.restore_requested.emit()

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        delta = event.angleDelta().y()
        if delta:
            self._vm.nudge_volume(5 if delta > 0 else -5)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space:
            self._vm.toggle_pause()
        elif event.key() == Qt.Key.Key_Escape:
            self.restore_requested.emit()
        else:
            super().keyPressEvent(event)

    # ---------------------------------------------------------------- рисунок

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        shape = QPainterPath()
        shape.addRoundedRect(body, RADIUS, RADIUS)
        painter.setClipPath(shape)
        self._paint_backdrop(painter, body)
        self._paint_meta(painter)
        self._paint_wave(painter)
        self._paint_times(painter)
        painter.setClipping(False)
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shape)
        painter.end()

    def _paint_backdrop(self, painter: QPainter, body: QRectF) -> None:
        painter.setOpacity(0.94)  # сквозь окно чуть видно то, что под ним
        if self._backdrop.isNull():
            base = QLinearGradient(body.topLeft(), body.bottomRight())
            base.setColorAt(0.0, self._palette.deep.darker(130))
            base.setColorAt(1.0, QColor(10, 12, 16))
            painter.fillRect(body, base)
        else:
            painter.drawImage(body, self._backdrop)
        shade = QLinearGradient(0, 0, 0, body.height())
        shade.setColorAt(0.0, QColor(8, 10, 14, 150))
        shade.setColorAt(1.0, QColor(8, 10, 14, 205))
        painter.fillRect(body, shade)
        painter.setOpacity(1.0)

    def _paint_meta(self, painter: QPainter) -> None:
        cover = QRectF(PAD, PAD, COVER, COVER)
        clip = QPainterPath()
        clip.addRoundedRect(cover, 10, 10)
        if self._thumb.isNull():
            painter.fillPath(clip, QColor(255, 255, 255, 26))
        else:
            painter.save()
            painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
            painter.drawPixmap(cover.toRect(), self._thumb)
            painter.restore()

        left = int(cover.right()) + 12
        width = self._restore.x() - 8 - left
        track = self._track
        title = track.title if track is not None else "Ничего не играет"
        author = track.author if track is not None else ""
        title_font = app_font(11, QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255))
        top = PAD + (8 if author else 16)
        painter.drawText(
            QRectF(left, top, width, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            QFontMetrics(title_font).elidedText(
                title, Qt.TextElideMode.ElideRight, width
            ),
        )
        if author:
            author_font = app_font(9)
            painter.setFont(author_font)
            painter.setPen(QColor(255, 255, 255, 165))
            painter.drawText(
                QRectF(left, top + 21, width, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(author_font).elidedText(
                    author, Qt.TextElideMode.ElideRight, width
                ),
            )

    def _paint_wave(self, painter: QPainter) -> None:
        left, right = float(PAD), float(WIDTH - PAD)
        span = right - left
        share = self._shown_position() / self._duration if self._duration > 0 else 0.0
        head = left + span * max(0.0, min(1.0, share))
        accent, second = self._palette.accent, self._palette.accent2
        seed = repr(self._track) if self._track is not None else ""

        if self._level > 0.01:
            room = BASELINE - WAVE_TOP
            for tint, shift, scale, alpha in (
                (second, 1.7, 0.7, 150),
                (accent, 0.0, 1.0, 255),
            ):
                heights = wave_heights(seed, self._phase + shift, self._level)
                points = [
                    QPointF(
                        left + span * i / (_POINTS - 1), BASELINE - h * room * scale
                    )
                    for i, h in enumerate(heights)
                ]
                curve = smooth_path(points)
                fill = QPainterPath(curve)
                fill.lineTo(right, BASELINE)
                fill.lineTo(left, BASELINE)
                glow = QLinearGradient(0, WAVE_TOP, 0, BASELINE)
                top_color, bottom = QColor(tint), QColor(tint)
                top_color.setAlpha(alpha // 4)
                bottom.setAlpha(0)
                glow.setColorAt(0.0, top_color)
                glow.setColorAt(1.0, bottom)
                painter.fillPath(fill, glow)
                line = QColor(tint)
                line.setAlpha(alpha)
                painter.setPen(QPen(line, 1.6))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(curve)

        painter.setPen(_round_pen(QColor(255, 255, 255, 46)))
        painter.drawLine(QPointF(left, BASELINE), QPointF(right, BASELINE))
        if self._duration <= 0:
            return
        played = QLinearGradient(left, 0, max(left + 1, head), 0)
        played.setColorAt(0.0, second)
        played.setColorAt(1.0, accent)
        painter.setPen(_round_pen(played))
        painter.drawLine(QPointF(left, BASELINE), QPointF(head, BASELINE))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(QPointF(head, BASELINE), 4.5, 4.5)

    def _paint_times(self, painter: QPainter) -> None:
        if self._duration <= 0:
            return
        painter.setFont(app_font(8.5))
        painter.setPen(QColor(255, 255, 255, 150))
        row = QRectF(PAD, HEIGHT - 10 - 42, WIDTH - 2 * PAD, 42)
        painter.drawText(
            row,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            resources.format_ms(self._shown_position()),
        )
        painter.drawText(
            row,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            resources.format_ms(self._duration),
        )
