"""Страница «Моя волна»: текущая волна крупно и карточки настроений.

Разделы: «Подобрано для вас» (колесо Яндекса — меняется после каждого
переключения), «Настроение», «Занятие», «Жанры», «Характер» — постоянный каталог.
"""

from __future__ import annotations

import math

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
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
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.services.async_wave import (
    WAVE_ACTIVITIES,
    WAVE_CHARACTER,
    WAVE_GENRES,
    WAVE_MOODS,
    WaveMood,
)
from quantis.ui.async_ui import schedule
from quantis.ui.preferences import UiPreferences
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.widgets.home_section import HomeSection
from quantis.ui.wave_art import WaveArtStore, mood_color, mood_kind, paint_wave_art

_SIDE_MARGIN = 28
_KIND_LABELS = {
    "mood": "Настроение",
    "activity": "Занятие",
    "combo": "Сочетание",
    "genre": "Жанр",
    "artist": "Артист",
    "character": "Характер",
    "control": "Волна",
}


def _display_font(pixel_size: int, weight: QFont.Weight) -> QFont:
    font = QFont(QApplication.font())
    font.setFamilies(list(UiPreferences().theme.fonts.families("display")))
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def _ui_font(pixel_size: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(QApplication.font())
    font.setPixelSize(pixel_size)
    font.setWeight(weight)
    return font


def _alpha(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, alpha)))
    return out


class WaveMoodCard(QWidget):
    """Карточка-«плитка»: арт во всю карточку, подпись поверх затемнения.

    Не круг и не квадрат: вытянутая плитка со срезанным углом — уголок
    заполняет цвет карточки, как закладка.
    """

    activated = Signal(object)

    W = 172
    H = 228
    RADIUS = 22.0
    NOTCH = 30.0

    def __init__(self, mood: WaveMood, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mood = mood
        self._active = False
        self._hover = 0.0
        self._phase = 0.0
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(mood.description or mood.name)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._bars = QTimer(self)
        self._bars.setInterval(60)
        self._bars.timeout.connect(self._tick)
        self._color = mood_color(mood)
        self._face_cache: QPixmap | None = None
        self._shadow_cache: QPixmap | None = None
        self._shadow_key: tuple | None = None
        self._face_key: tuple | None = None
        self._paths_key: tuple[float, float] | None = None
        self._paths_cache: tuple[QPainterPath, list[QPainterPath]]
        WaveArtStore.instance().updated.connect(self._invalidate)

    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hover = Property(float, _get_hover, _set_hover)

    def set_active(self, active: bool, *, animate: bool = True) -> None:
        if active != self._active:
            self._active = active
            self._face_cache = None
            self.update()
        if active and animate:
            if not self._bars.isActive():
                self._bars.start()
        else:
            self._bars.stop()

    def _tick(self) -> None:
        self._phase += 0.35
        # только угол с эквалайзером, не всю карточку
        self.update(self.width() - 46, self.height() - 44, 40, 34)

    def enterEvent(self, event) -> None:
        self._animate_hover(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_hover(0.0)
        super().leaveEvent(event)

    def _animate_hover(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.activated.emit(self.mood)
        super().mouseReleaseEvent(event)

    def _shape(self, rect: QRectF) -> QPainterPath:
        """Скругления везде, кроме правого верхнего — там срез."""
        r, n = self.RADIUS, self.NOTCH
        path = QPainterPath()
        path.moveTo(rect.left() + r, rect.top())
        path.lineTo(rect.right() - n, rect.top())
        path.lineTo(rect.right(), rect.top() + n)
        path.lineTo(rect.right(), rect.bottom() - r)
        path.quadTo(rect.right(), rect.bottom(), rect.right() - r, rect.bottom())
        path.lineTo(rect.left() + r, rect.bottom())
        path.quadTo(rect.left(), rect.bottom(), rect.left(), rect.bottom() - r)
        path.lineTo(rect.left(), rect.top() + r)
        path.quadTo(rect.left(), rect.top(), rect.left() + r, rect.top())
        path.closeSubpath()
        return path

    def _paths(self, w: float, h: float) -> tuple[QPainterPath, list[QPainterPath]]:
        """Контур и два слоя тени — строятся раз на размер карточки."""
        if self._paths_key != (w, h):
            rect = QRectF(0, 0, w, h)
            glows = [
                self._shape(rect.adjusted(-spread / 3, spread / 2, spread / 3, spread))
                for spread in (10, 5)
            ]
            self._paths_cache = (self._shape(rect), glows)
            self._paths_key = (w, h)
        return self._paths_cache

    def _face(self, w: float, h: float) -> QPixmap:
        """Арт + затемнение + уголок + подписи. Меняется редко (размер,
        «сейчас играет», догрузилась обложка) — рисуем один раз в pixmap,
        а на кадре прокрутки и наведения только копируем его."""
        dpr = self.devicePixelRatioF()
        key = (w, h, dpr, self._active)
        if self._face_cache is not None and self._face_key == key:
            return self._face_cache
        pixmap = QPixmap(round(w * dpr), round(h * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, w, h)
        shape, _ = self._paths(w, h)
        painter.save()
        painter.setClipPath(shape)
        paint_wave_art(painter, rect, self.mood)
        shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shade.setColorAt(0.40, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 215))
        painter.fillRect(rect, shade)
        painter.restore()
        n = self.NOTCH
        corner = QPainterPath()
        corner.moveTo(rect.right() - n + 6, rect.top())
        corner.lineTo(rect.right(), rect.top() + n - 6)
        corner.lineTo(rect.right(), rect.top())
        corner.closeSubpath()
        painter.fillPath(corner, _alpha(self._color, 235))
        border, width = QColor(255, 255, 255, 30), 1.0
        if self._active:
            border, width = QColor(self._color).lighter(130), 2.2
        painter.setPen(QPen(border, width))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(shape)
        self._paint_text(painter, rect, self._color)
        painter.end()
        self._face_cache, self._face_key = pixmap, key
        return pixmap

    def _shadow(self, w: float, h: float) -> QPixmap:
        """Два слоя тени при максимальном наведении; яркость — opacity."""
        dpr = self.devicePixelRatioF()
        key = (w, h, dpr)
        if self._shadow_cache is not None and self._shadow_key == key:
            return self._shadow_cache
        pixmap = QPixmap(round((w + 8) * dpr), round((h + 16) * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(4, 4)
        _, glows = self._paths(w, h)
        for glow, alpha in zip(glows, (18, 30), strict=True):
            painter.fillPath(glow, _alpha(self._color, int(alpha * 1.4)))
        painter.end()
        self._shadow_cache, self._shadow_key = pixmap, key
        return pixmap

    def _invalidate(self) -> None:
        self._face_cache = None
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._color
        w, h = self.width() - 6.0, self.height() - 10.0
        painter.translate(3, 5 - 4.0 * self._hover)
        shape, _ = self._paths(w, h)

        # Тень в цвет карточки — сильнее при наведении. Тень, арт и рамка
        # покоя — готовые pixmap: на кадре прокрутки только два drawPixmap.
        painter.setOpacity((0.4 + self._hover) / 1.4)
        painter.drawPixmap(-4, -4, self._shadow(w, h))
        painter.setOpacity(1.0)
        painter.drawPixmap(0, 0, self._face(w, h))
        if self._hover > 0:
            painter.fillPath(shape, QColor(255, 255, 255, int(16 * self._hover)))
            if not self._active:
                painter.setPen(QPen(QColor(255, 255, 255, int(40 * self._hover)), 1.0))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(shape)
        if self._active:
            self._paint_bars(painter, QRectF(0, 0, w, h), color)
        painter.end()

    def _paint_text(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        pad = 14.0
        label = _KIND_LABELS.get(mood_kind(self.mood), "")
        if self._active:
            label = "Сейчас играет"
        small = _ui_font(10, QFont.Weight.Bold)
        small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        painter.setFont(small)
        metrics = QFontMetricsF(small)
        pill_w = metrics.horizontalAdvance(label.upper()) + 16
        pill = QRectF(rect.left() + pad - 2, rect.top() + pad - 2, pill_w, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.drawRoundedRect(pill, 10, 10)
        painter.setPen(QColor(255, 255, 255, 220))
        painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, label.upper())

        width = rect.width() - 2 * pad - (22 if self._active else 0)
        title_font, height = self._fit_title(width)
        painter.setFont(title_font)
        painter.setPen(QColor(255, 255, 255))
        text_rect = QRectF(
            rect.left() + pad, rect.bottom() - pad - height, width, height
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignBottom
            | Qt.AlignmentFlag.AlignLeft
            | Qt.TextFlag.TextWordWrap,
            self.mood.name,
        )

    def _fit_title(self, width: float) -> tuple[QFont, float]:
        """Название — не больше трёх строк: длинные мельчают."""
        for size in (15, 14, 13, 12):
            font = _display_font(size, QFont.Weight.Bold)
            metrics = QFontMetricsF(font)
            box = metrics.boundingRect(
                QRectF(0, 0, width, 1000),
                Qt.TextFlag.TextWordWrap,
                self.mood.name,
            )
            longest = max(metrics.horizontalAdvance(w) for w in self.mood.name.split())
            lines = 2 if size > 13 else 3
            if longest <= width and box.height() <= metrics.lineSpacing() * lines + 1:
                return font, box.height()
        return font, min(box.height(), metrics.lineSpacing() * 3)

    def _paint_bars(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        base_x = rect.right() - 30
        base_y = rect.bottom() - 16
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color).lighter(140))
        for i in range(4):
            level = 0.35 + 0.65 * abs(math.sin(self._phase + i * 1.3))
            h = 4 + 14 * level
            painter.drawRoundedRect(QRectF(base_x + i * 5, base_y - h, 3, h), 1.5, 1.5)


class _CardFlow(QWidget):
    """Карточки рядами с переносом: ряд тянется на всю ширину, карточки
    растут от ``MIN_W`` до ``MAX_W``, пропорции плитки сохраняются."""

    GAP = 16
    MIN_W = 160
    MAX_W = 212
    RATIO = WaveMoodCard.H / WaveMoodCard.W

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: list[WaveMoodCard] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def cards(self) -> list[WaveMoodCard]:
        return list(self._cards)

    def set_cards(self, cards: list[WaveMoodCard]) -> None:
        for card in self._cards:
            card.deleteLater()
        self._cards = cards
        for card in cards:
            card.setParent(self)
            card.show()
        self._relayout()

    def card_size(self, width: int) -> tuple[int, int, int]:
        """(колонок, ширина карточки, высота карточки) для ширины ряда."""
        cols = max(1, (width + self.GAP) // (self.MIN_W + self.GAP))
        card_w = (width - (cols - 1) * self.GAP) // cols
        card_w = max(self.MIN_W, min(self.MAX_W, card_w))
        return cols, card_w, round(card_w * self.RATIO)

    def heightForWidth(self, width: int) -> int:
        if not self._cards:
            return 0
        cols, _, card_h = self.card_size(width)
        rows = math.ceil(len(self._cards) / cols)
        return rows * card_h + (rows - 1) * self.GAP

    def hasHeightForWidth(self) -> bool:
        return True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        width = max(self.width(), self.MIN_W)
        cols, card_w, card_h = self.card_size(width)
        for index, card in enumerate(self._cards):
            row, col = divmod(index, cols)
            card.setFixedSize(card_w, card_h)
            card.move(col * (card_w + self.GAP), row * (card_h + self.GAP))
        self.setFixedHeight(self.heightForWidth(width))


class WaveHero(QFrame):
    """Шапка: арт текущей волны, название и кнопки управления."""

    play_requested = Signal()
    reshuffle_requested = Signal()
    reset_requested = Signal()

    ART = 212
    HEIGHT = 268

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("waveHero")
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._mood: WaveMood | None = None
        self._state = "idle"
        self._phase = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(28 + self.ART + 32, 0, 28, 0)
        layout.setSpacing(0)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(10)
        column.addStretch(1)
        column.addSpacing(110)  # место под подпись и название (рисуются в paint)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self._play = self._button("▶  Слушать", "waveHeroPlay")
        self._play.clicked.connect(self.play_requested.emit)
        self._shuffle = self._button("Встряхнуть", "waveHeroAction")
        self._shuffle.setToolTip("Та же волна, но непривычные треки")
        self._shuffle.clicked.connect(self.reshuffle_requested.emit)
        self._reset = self._button("Назад к привычному", "waveHeroAction")
        self._reset.clicked.connect(self.reset_requested.emit)
        for button in (self._play, self._shuffle, self._reset):
            buttons.addWidget(button)
        buttons.addStretch(1)
        column.addLayout(buttons)
        column.addStretch(1)
        layout.addLayout(column, stretch=1)

        self._ticker = QTimer(self)
        self._ticker.setInterval(50)
        self._ticker.timeout.connect(self._tick)
        self._layers: dict[str, tuple[tuple, QPixmap]] = {}
        WaveArtStore.instance().updated.connect(self._invalidate)

    @staticmethod
    def _button(text: str, name: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setText(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def set_mood(self, mood: WaveMood, *, is_default: bool) -> None:
        self._mood = mood
        self._reset.setVisible(not is_default)
        self.update()

    def set_state(self, state: str, *, busy: bool = False, eco: bool = False) -> None:
        """``idle`` — волна не в плеере, ``playing`` / ``paused`` — в плеере."""
        self._state = state
        self._play.setText(
            {"playing": "❚❚  Пауза", "paused": "▶  Продолжить"}.get(state, "▶  Слушать")
        )
        for button in (self._play, self._shuffle, self._reset):
            button.setEnabled(not busy)
        if state == "playing" and not eco:
            self._ticker.start()
        else:
            self._ticker.stop()
        self.update()

    def _tick(self) -> None:
        self._phase += 0.06
        # пульсирует только свечение у арта — остальная шапка из кэша
        self.update(self._glow_rect().toAlignedRect())

    def _art_rect(self) -> QRectF:
        return QRectF(28, (self.height() - self.ART) / 2, self.ART, self.ART)

    def _layer(self, key: tuple, paint) -> QPixmap:
        """Статичный слой шапки в pixmap — перерисовывается при смене ключа."""
        cached = self._layers.get(paint.__name__)
        if cached is not None and cached[0] == key:
            return cached[1]
        dpr = self.devicePixelRatioF()
        pixmap = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint(painter)
        painter.end()
        self._layers[paint.__name__] = (key, pixmap)
        return pixmap

    def _paint_backdrop(self, painter: QPainter) -> None:
        """Фон — тот же арт, растянутый и притушенный: «аура» волны."""
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        frame = QPainterPath()
        frame.addRoundedRect(rect, 28, 28)
        painter.save()
        painter.setClipPath(frame)
        painter.setOpacity(0.55)
        paint_wave_art(painter, rect.adjusted(-60, -160, 60, 160), self._mood)
        painter.setOpacity(1.0)
        veil = QLinearGradient(rect.topLeft(), rect.topRight())
        veil.setColorAt(0.0, QColor(6, 7, 12, 120))
        veil.setColorAt(0.45, QColor(6, 7, 12, 205))
        veil.setColorAt(1.0, QColor(6, 7, 12, 235))
        painter.fillRect(rect, veil)
        painter.restore()
        painter.setPen(QPen(_alpha(mood_color(self._mood), 90), 1.2))
        painter.drawPath(frame)
        self._paint_titles(painter, mood_color(self._mood))

    def _paint_cover(self, painter: QPainter) -> None:
        art = self._art_rect()
        art_path = QPainterPath()
        art_path.addRoundedRect(art, 26, 26)
        painter.save()
        painter.setClipPath(art_path)
        paint_wave_art(painter, art, self._mood)
        painter.restore()
        painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
        painter.drawPath(art_path)

    def _invalidate(self) -> None:
        self._layers.clear()
        self.update()

    def paintEvent(self, event) -> None:
        if self._mood is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        size_key = (self.width(), self.height(), self.devicePixelRatioF(), self._mood)
        painter.drawPixmap(
            0, 0, self._layer((*size_key, self._state), self._paint_backdrop)
        )

        # Свечение вокруг арта — единственное, что меняется каждый кадр
        art = self._art_rect()
        color = mood_color(self._mood)
        pulse = (
            0.5 + 0.5 * math.sin(self._phase * 2) if self._state == "playing" else 0.25
        )
        glow = QRadialGradient(art.center(), self.ART * (0.80 + 0.06 * pulse))
        glow.setColorAt(0.55, _alpha(color, int(90 + 70 * pulse)))
        glow.setColorAt(1.0, _alpha(color, 0))
        frame = QPainterPath()
        frame.addRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 28, 28)
        painter.save()
        painter.setClipPath(frame)
        painter.fillRect(self._glow_rect(), glow)
        painter.restore()
        painter.drawPixmap(0, 0, self._layer(size_key, self._paint_cover))
        painter.end()

    def _glow_rect(self) -> QRectF:
        return self._art_rect().adjusted(-90, -90, 90, 90)

    def _paint_titles(self, painter: QPainter, color: QColor) -> None:
        left = 28 + self.ART + 32
        width = self.width() - left - 28
        top = (self.height() - 190) / 2

        small = _ui_font(11, QFont.Weight.Bold)
        small.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
        painter.setFont(small)
        painter.setPen(QColor(color).lighter(150))
        caption = {
            "playing": "СЕЙЧАС В ВОЛНЕ",
            "paused": "ВОЛНА НА ПАУЗЕ",
        }.get(self._state, "МОЯ ВОЛНА")
        painter.drawText(
            QRectF(left, top, width, 18), Qt.AlignmentFlag.AlignLeft, caption
        )

        title = _display_font(34, QFont.Weight.Bold)
        metrics = QFontMetricsF(title)
        name = metrics.elidedText(self._mood.name, Qt.TextElideMode.ElideRight, width)
        painter.setFont(title)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(
            QRectF(left, top + 22, width, 48), Qt.AlignmentFlag.AlignLeft, name
        )

        description = self._mood.description or "Поток треков под это настроение"
        painter.setFont(_ui_font(13))
        painter.setPen(QColor(255, 255, 255, 170))
        painter.drawText(
            QRectF(left, top + 74, width, 20), Qt.AlignmentFlag.AlignLeft, description
        )


class WavePage(QWidget):
    """Отдельная страница «Моей волны» в боковом меню."""

    toggle_pause_requested = Signal()

    def __init__(
        self,
        view_model: HomeViewModel,
        bridge: AsyncBridge | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("wavePage")
        self._vm = view_model
        self._bridge = bridge
        self._playing = False
        self._eco = False
        WaveArtStore.instance().set_bridge(bridge)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("waveScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("waveScrollContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(_SIDE_MARGIN, 20, _SIDE_MARGIN, 40)
        layout.setSpacing(30)

        self._hero = WaveHero()
        self._hero.play_requested.connect(self._on_play)
        self._hero.reshuffle_requested.connect(self._on_reshuffle)
        self._hero.reset_requested.connect(self._on_reset)
        layout.addWidget(self._hero)

        self._sections: list[tuple[HomeSection, _CardFlow]] = []
        self._picks = self._add_section(
            layout, "Подобрано для вас", "Меняется после каждого выбора"
        )
        self._moods = self._add_section(layout, "Настроение")
        self._activities = self._add_section(layout, "Занятие")
        self._genres = self._add_section(layout, "Жанры")
        self._character = self._add_section(layout, "Характер")
        self._moods.set_cards(self._make_cards(WAVE_MOODS))
        self._activities.set_cards(self._make_cards(WAVE_ACTIVITIES))
        self._genres.set_cards(self._make_cards(WAVE_GENRES))
        self._character.set_cards(self._make_cards(WAVE_CHARACTER))
        layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._vm.wave_moods_changed.connect(self._sync)
        self._sync()

    def _add_section(
        self, layout: QVBoxLayout, title: str, subtitle: str = ""
    ) -> _CardFlow:
        section = HomeSection(title, subtitle)
        flow = _CardFlow()
        section.add_widget_block(flow)
        layout.addWidget(section)
        self._sections.append((section, flow))
        return flow

    def _make_cards(self, moods) -> list[WaveMoodCard]:
        cards = []
        for mood in moods:
            card = WaveMoodCard(mood)
            card.activated.connect(self._on_mood)
            cards.append(card)
        return cards

    # --- состояние ---------------------------------------------------------

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self._sync_state()

    def set_eco(self, enabled: bool) -> None:
        self._eco = enabled
        self._sync_state()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._vm.wave_moods and self._bridge is not None:
            schedule(self._vm.refresh_wave_moods(), self._bridge)
        self._sync()

    def _sync(self) -> None:
        picks = [
            m
            for m in self._vm.wave_moods
            if not m.is_control and mood_kind(m) != "character"
        ]
        current = [card.mood for card in self._picks.cards()]
        if picks != current:
            self._picks.set_cards(self._make_cards(picks))
        self._sections[0][0].setVisible(bool(picks))
        active = self._vm.active_wave_mood
        self._hero.set_mood(active, is_default=active.seeds == ("user:onyourwave",))
        self._sync_state()

    def _sync_state(self) -> None:
        current = self._vm.wave_is_current
        state = "idle"
        if current:
            state = "playing" if self._playing else "paused"
        busy = self._vm.wave_mood_busy
        self._hero.set_state(state, busy=busy, eco=self._eco)
        active_seeds = self._vm.active_wave_seeds
        for _, flow in self._sections:
            for card in flow.cards():
                is_active = current and card.mood.seeds == active_seeds
                card.set_active(is_active, animate=self._playing and not self._eco)
                card.setEnabled(not busy)

    # --- действия ------------------------------------------------------------

    def _on_mood(self, mood: WaveMood) -> None:
        if self._bridge is None:
            return
        if self._vm.wave_is_current and mood.seeds == self._vm.active_wave_seeds:
            self.toggle_pause_requested.emit()
            return
        schedule(self._vm.play_wave_mood(mood), self._bridge)

    def _on_play(self) -> None:
        if self._bridge is None:
            return
        if self._vm.wave_is_current:
            self.toggle_pause_requested.emit()
            return
        schedule(self._vm.play_wave(), self._bridge)

    def _control(self, prefix: str) -> WaveMood | None:
        for mood in self._vm.wave_moods:
            if mood.id.startswith(prefix):
                return mood
        return None

    def _on_reshuffle(self) -> None:
        mood = self._control("diversity:reshuffle")
        if mood is None:
            import time

            mood = WaveMood(
                id="diversity:reshuffle",
                name="Встряхнуть Мою волну",
                seeds=(f"diversity:reshuffle_{int(time.time() * 1000)}",),
                style="CONTROL_ACCENT",
            )
        self._on_mood(mood)

    def _on_reset(self) -> None:
        mood = self._control("user:onyourwave")
        if mood is None:
            from quantis.services.async_wave import DEFAULT_WAVE_MOOD

            mood = DEFAULT_WAVE_MOOD
        self._on_mood(mood)

    def sizeHint(self) -> QSize:
        return QSize(900, 700)
