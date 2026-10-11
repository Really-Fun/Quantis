"""«Карта настроения»: настроения и занятия на плоскости эмоций.

По горизонтали — энергия (спокойнее → энергичнее), по вертикали — окраска
(грустнее → светлее): модель эмоций Рассела. Настроения — круги, занятия —
скруглённые квадраты. Выбрать можно одно настроение и одно занятие сразу —
волна смешает их (сиды ``mood:…`` + ``activity:…``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QSizePolicy, QWidget

from quantis.services.async_wave import WAVE_ACTIVITIES, WAVE_MOODS, WaveMood
from quantis.ui.wave_art import WaveArtStore, mood_color, paint_wave_art


@dataclass(frozen=True)
class FieldNode:
    mood: WaveMood
    short: str
    x: float
    """Энергия: 0 — спокойнее, 1 — энергичнее."""
    y: float
    """Окраска: 0 — грустнее, 1 — светлее."""
    kind: str  # "mood" | "activity"

    @property
    def seed(self) -> str:
        return self.mood.seeds[0]


def _by_seed(moods: tuple[WaveMood, ...]) -> dict[str, WaveMood]:
    return {m.seeds[0]: m for m in moods}


_MOOD = _by_seed(WAVE_MOODS)
_ACT = _by_seed(WAVE_ACTIVITIES)

# Места подобраны вручную: смысл (где на шкалах живёт настроение) + чтобы
# узлы с подписями не налезали друг на друга на поле ~800×480.
NODES: tuple[FieldNode, ...] = (
    FieldNode(_MOOD["mood:dream"], "Мечты", 0.13, 0.86, "mood"),
    FieldNode(_MOOD["mood:beautiful"], "Красота", 0.38, 0.92, "mood"),
    FieldNode(_MOOD["mood:happy"], "Радость", 0.64, 0.86, "mood"),
    FieldNode(_MOOD["mood:energetic"], "Энергия", 0.90, 0.70, "mood"),
    FieldNode(_MOOD["mood:calm"], "Спокойно", 0.24, 0.62, "mood"),
    FieldNode(_MOOD["mood:sentimental"], "Нежность", 0.36, 0.36, "mood"),
    FieldNode(_MOOD["mood:autumn"], "Осень", 0.14, 0.27, "mood"),
    FieldNode(_MOOD["mood:sad"], "Грусть", 0.30, 0.07, "mood"),
    FieldNode(_ACT["activity:fall-asleep"], "Сон", 0.04, 0.50, "activity"),
    FieldNode(_ACT["activity:work-background"], "Работа", 0.52, 0.50, "activity"),
    FieldNode(_ACT["activity:romantic-date"], "Свидание", 0.50, 0.73, "activity"),
    FieldNode(_ACT["activity:road-trip"], "Дорога", 0.70, 0.50, "activity"),
    FieldNode(_ACT["activity:party"], "Вечеринка", 0.86, 0.96, "activity"),
    FieldNode(_ACT["activity:run"], "Бег", 0.92, 0.38, "activity"),
    FieldNode(_ACT["activity:workout"], "Спорт", 0.74, 0.16, "activity"),
)

NODE_BY_SEED = {node.seed: node for node in NODES}

# Цвета квадрантов фона: светло-спокойно, светло-энергично, напряжённо, грустно.
_QUADRANTS = (
    (0.0, 0.0, "#21C2B0"),
    (1.0, 0.0, "#FFB020"),
    (1.0, 1.0, "#FF4A2A"),
    (0.0, 1.0, "#4257FF"),
)

_MOOD_D = 74.0
_ACT_D = 62.0
_PAD_X = 64.0
_PAD_TOP = 52.0
_PAD_BOTTOM = 70.0
_RADIUS = 28.0


def _alpha(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, alpha)))
    return out


def _font(pixel_size: int, weight: QFont.Weight, spacing: float = 0.0) -> QFont:
    font = QFont(QApplication.font())
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def node_shape(node: FieldNode, rect: QRectF) -> QPainterPath:
    path = QPainterPath()
    if node.kind == "mood":
        path.addEllipse(rect)
    else:
        path.addRoundedRect(rect, rect.width() * 0.3, rect.width() * 0.3)
    return path


class MoodField(QWidget):
    """Поле с узлами. Клик — выбрать/снять, двойной клик — сразу играть."""

    selection_changed = Signal(object, object)
    """(сид настроения | None, сид занятия | None)"""
    play_requested = Signal()

    MIN_HEIGHT = 440

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("moodField")
        self.setMouseTracking(True)
        self.setMinimumHeight(self.MIN_HEIGHT)
        self.setMinimumWidth(520)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._mood_seed: str | None = None
        self._activity_seed: str | None = None
        self._active: tuple[str, ...] = ()
        self._playing = False
        self._eco = False
        self._hover: FieldNode | None = None
        self._phase = 0.0
        self._bg: QPixmap | None = None
        self._bg_key: tuple | None = None
        self._orbs: dict[tuple, QPixmap] = {}
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        WaveArtStore.instance().updated.connect(self._invalidate_orbs)

    # --- состояние -----------------------------------------------------------

    def selection(self) -> tuple[str | None, str | None]:
        return self._mood_seed, self._activity_seed

    def set_selection(self, mood_seed: str | None, activity_seed: str | None) -> None:
        if (mood_seed, activity_seed) == (self._mood_seed, self._activity_seed):
            return
        self._mood_seed, self._activity_seed = mood_seed, activity_seed
        self.update()

    def set_active(self, seeds: tuple[str, ...], *, playing: bool) -> None:
        """Сиды играющей волны (кольца-пульс вокруг их узлов)."""
        self._active = tuple(s for s in seeds if s in NODE_BY_SEED)
        self._playing = playing
        self._sync_timer()
        self.update()

    def set_eco(self, enabled: bool) -> None:
        self._eco = enabled
        self._sync_timer()

    def _sync_timer(self) -> None:
        run = bool(self._active) and self._playing and not self._eco
        run = run and self.isVisible()
        if run and not self._timer.isActive():
            self._timer.start()
        elif not run:
            self._timer.stop()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        self._sync_timer()

    def _tick(self) -> None:
        self._phase = (self._phase + 0.04) % 1.0
        # Только области вокруг играющих узлов — не всё поле.
        for seed in self._active:
            node = NODE_BY_SEED[seed]
            center = self.node_center(node)
            r = int(self._diameter(node) / 2 + 40)
            self.update(QRect(int(center.x()) - r, int(center.y()) - r, 2 * r, 2 * r))

    # --- геометрия -------------------------------------------------------------

    def _inner(self) -> QRectF:
        return QRectF(self.rect()).adjusted(_PAD_X, _PAD_TOP, -_PAD_X, -_PAD_BOTTOM)

    def node_center(self, node: FieldNode) -> QPointF:
        inner = self._inner()
        return QPointF(
            inner.left() + node.x * inner.width(),
            inner.top() + (1 - node.y) * inner.height(),
        )

    @staticmethod
    def _diameter(node: FieldNode) -> float:
        return _MOOD_D if node.kind == "mood" else _ACT_D

    def _is_selected(self, node: FieldNode) -> bool:
        return node.seed in (self._mood_seed, self._activity_seed)

    def node_at(self, pos: QPointF) -> FieldNode | None:
        best, best_d = None, 1e9
        for node in NODES:
            d = math.dist(
                (pos.x(), pos.y()),
                (self.node_center(node).x(), self.node_center(node).y()),
            )
            if d <= self._diameter(node) / 2 + 6 and d < best_d:
                best, best_d = node, d
        return best

    # --- мышь ------------------------------------------------------------------

    def mouseMoveEvent(self, event) -> None:
        node = self.node_at(event.position())
        if node is not self._hover:
            old, self._hover = self._hover, node
            for changed in (old, node):
                if changed is not None:
                    self._update_node(changed)
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if node is not None
                else Qt.CursorShape.ArrowCursor
            )
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        if self._hover is not None:
            old, self._hover = self._hover, None
            self._update_node(old)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            node = self.node_at(event.position())
            if node is not None:
                self.toggle(node)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        node = self.node_at(event.position())
        if node is not None and event.button() == Qt.MouseButton.LeftButton:
            # Двойной клик = «играть это»: первый клик уже выбрал узел.
            if not self._is_selected(node):
                self.toggle(node)
            self.play_requested.emit()
            return
        super().mouseDoubleClickEvent(event)

    def toggle(self, node: FieldNode) -> None:
        mood, activity = self._mood_seed, self._activity_seed
        if node.kind == "mood":
            mood = None if mood == node.seed else node.seed
        else:
            activity = None if activity == node.seed else node.seed
        self.set_selection(mood, activity)
        self.selection_changed.emit(mood, activity)

    def _update_node(self, node: FieldNode) -> None:
        center = self.node_center(node)
        r = int(self._diameter(node) / 2 + 34)
        self.update(QRect(int(center.x()) - r, int(center.y()) - r, 2 * r, 2 * r + 24))

    # --- рисование ---------------------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._bg = None

    def _invalidate_orbs(self) -> None:
        self._orbs.clear()
        self.update()

    def _background(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (self.width(), self.height(), dpr)
        if self._bg is not None and self._bg_key == key:
            return self._bg
        pixmap = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        frame = QPainterPath()
        frame.addRoundedRect(rect, _RADIUS, _RADIUS)
        p.setClipPath(frame)
        p.fillRect(rect, QColor(9, 10, 17, 236))
        w, h = rect.width(), rect.height()
        for fx, fy, hex_color in _QUADRANTS:
            glow = QRadialGradient(QPointF(fx * w, fy * h), max(w, h) * 0.62)
            color = QColor(hex_color)
            glow.setColorAt(0.0, _alpha(color, 78))
            glow.setColorAt(0.55, _alpha(color, 22))
            glow.setColorAt(1.0, _alpha(color, 0))
            p.fillRect(rect, glow)

        # Точечная сетка
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 20))
        step = 28
        y = rect.top() + step / 2
        while y < rect.bottom():
            x = rect.left() + step / 2
            while x < rect.right():
                p.drawEllipse(QPointF(x, y), 1.0, 1.0)
                x += step
            y += step

        # Оси через центр поля
        inner = self._inner()
        cx, cy = inner.center().x(), inner.center().y()
        pen = QPen(QColor(255, 255, 255, 38), 1.0, Qt.PenStyle.DashLine)
        pen.setDashPattern([3, 6])
        p.setPen(pen)
        p.drawLine(QPointF(rect.left() + 18, cy), QPointF(rect.right() - 18, cy))
        p.drawLine(QPointF(cx, rect.top() + 18), QPointF(cx, rect.bottom() - 18))

        label = _font(10, QFont.Weight.Bold, 1.4)
        p.setFont(label)
        metrics = QFontMetricsF(label)
        for text, anchor in (
            ("← СПОКОЙНЕЕ", "left"),
            ("ЭНЕРГИЧНЕЕ →", "right"),
            ("↑ СВЕТЛЕЕ", "top"),
            ("↓ ГРУСТНЕЕ", "bottom"),
        ):
            tw = metrics.horizontalAdvance(text) + 18
            # Боковые подписи — в нижних углах: у краёв оси живут «Сон» и «Бег».
            if anchor == "left":
                box = QRectF(rect.left() + 16, rect.bottom() - 34, tw, 22)
            elif anchor == "right":
                box = QRectF(rect.right() - 16 - tw, rect.bottom() - 34, tw, 22)
            elif anchor == "top":
                box = QRectF(cx - tw / 2, rect.top() + 12, tw, 22)
            else:
                box = QRectF(cx - tw / 2, rect.bottom() - 34, tw, 22)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(9, 10, 17, 190))
            p.drawRoundedRect(box, 11, 11)
            p.setPen(QColor(255, 255, 255, 140))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(frame)
        p.end()
        self._bg, self._bg_key = pixmap, key
        return pixmap

    def _orb(self, node: FieldNode, selected: bool) -> QPixmap:
        """Узел с артом, кольцом и подписью — в кэше на (узел, выбран, dpr)."""
        dpr = self.devicePixelRatioF()
        key = (node.seed, selected, dpr)
        cached = self._orbs.get(key)
        if cached is not None:
            return cached
        d = self._diameter(node)
        size = d + 40  # поля под кольцо и подпись
        pixmap = QPixmap(round(size * dpr), round((size + 26) * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = mood_color(node.mood)
        art = QRectF(20, 20, d, d)
        shape = node_shape(node, art)
        p.save()
        p.setClipPath(shape)
        paint_wave_art(p, art, node.mood)
        if not selected:
            p.fillRect(art, QColor(6, 7, 12, 70))  # невыбранные чуть приглушены
        p.restore()
        ring = QPen(
            QColor(255, 255, 255, 235) if selected else _alpha(color, 170),
            3.0 if selected else 1.6,
        )
        p.setPen(ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape)

        font = _font(12, QFont.Weight.Bold)
        p.setFont(font)
        metrics = QFontMetricsF(font)
        tw = metrics.horizontalAdvance(node.short) + 16
        pill = QRectF(size / 2 - tw / 2, 20 + d + 7, tw, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_alpha(color, 235) if selected else QColor(9, 10, 17, 200))
        p.drawRoundedRect(pill, 10, 10)
        p.setPen(QColor(10, 10, 14) if selected else QColor(255, 255, 255, 225))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, node.short)
        p.end()
        self._orbs[key] = pixmap
        return pixmap

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(0, 0, self._background())
        self._paint_link(painter)
        for node in NODES:
            self._paint_node(painter, node)
        painter.end()

    def _paint_link(self, painter: QPainter) -> None:
        """Связь «настроение + занятие» — дуга между выбранными узлами."""
        if not (self._mood_seed and self._activity_seed):
            return
        a = self.node_center(NODE_BY_SEED[self._mood_seed])
        b = self.node_center(NODE_BY_SEED[self._activity_seed])
        mid = (a + b) / 2
        normal = QPointF(-(b.y() - a.y()), b.x() - a.x())
        length = math.hypot(normal.x(), normal.y()) or 1.0
        bend = min(60.0, length * 0.18)
        ctrl = mid + normal / length * bend
        path = QPainterPath(a)
        path.quadTo(ctrl, b)
        grad = QLinearGradient(a, b)
        grad.setColorAt(0, mood_color(NODE_BY_SEED[self._mood_seed].mood))
        grad.setColorAt(1, mood_color(NODE_BY_SEED[self._activity_seed].mood))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        wide = QPen(grad, 10.0)
        wide.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setOpacity(0.22)
        painter.setPen(wide)
        painter.drawPath(path)
        painter.setOpacity(1.0)
        thin = QPen(grad, 2.2, Qt.PenStyle.DashLine)
        thin.setDashPattern([4, 4])
        thin.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(thin)
        painter.drawPath(path)

    def _paint_node(self, painter: QPainter, node: FieldNode) -> None:
        center = self.node_center(node)
        d = self._diameter(node)
        selected = self._is_selected(node)
        color = mood_color(node.mood)
        if node.seed in self._active:
            self._paint_pulse(painter, node, center, d, color)
        if selected:
            halo = QRadialGradient(center, d * 0.95)
            halo.setColorAt(0.45, _alpha(color, 120))
            halo.setColorAt(1.0, _alpha(color, 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(center, d * 0.95, d * 0.95)
        orb = self._orb(node, selected)
        scale = 1.08 if node is self._hover else 1.0
        w = orb.width() / orb.devicePixelRatio() * scale
        h = orb.height() / orb.devicePixelRatio() * scale
        offset = (d / 2 + 20) * scale
        painter.drawPixmap(
            QRectF(center.x() - offset, center.y() - offset, w, h),
            orb,
            QRectF(orb.rect()),
        )

    def _paint_pulse(
        self,
        painter: QPainter,
        node: FieldNode,
        center: QPointF,
        d: float,
        color: QColor,
    ) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        phases = (self._phase, (self._phase + 0.5) % 1.0) if self._playing else (0.3,)
        for t in phases:
            r = d / 2 + 4 + t * 30
            painter.setPen(QPen(_alpha(color, int(170 * (1 - t))), 2.0))
            if node.kind == "mood":
                painter.drawEllipse(center, r, r)
            else:
                rect = QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r)
                painter.drawRoundedRect(rect, r * 0.6, r * 0.6)
