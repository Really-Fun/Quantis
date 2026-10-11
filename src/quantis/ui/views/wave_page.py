"""Страница «Моя волна»: карта настроения слева, главное — справа.

Карта (``MoodField``) — настроения и занятия на плоскости «энергия × окраска»;
можно смешать настроение с занятием. Панель справа — текущая или собранная
волна крупно, запуск и очередь. Ниже — «Подобрано для вас» (колесо Яндекса),
«Жанры», «Характер».
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
    QBoxLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track
from quantis.services.async_wave import (
    DEFAULT_WAVE_MOOD,
    WAVE_CHARACTER,
    WAVE_GENRES,
    WaveMood,
)
from quantis.ui.async_ui import schedule
from quantis.ui.preferences import UiPreferences
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.widgets.cover_art import (
    CoverDecoder,
    paint_rounded_cover,
    request_track_cover,
)
from quantis.ui.views.widgets.home_section import HomeSection
from quantis.ui.views.widgets.mood_field import NODE_BY_SEED, MoodField
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


class _PanelArt(QWidget):
    """Обложка волны в панели: арт + мягкое свечение в её цвет (в кэше)."""

    ART = 164
    GLOW = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        side = self.ART + 2 * self.GLOW
        self.setFixedSize(side, side)
        self._mood: WaveMood | None = None
        self._cache: tuple[tuple, QPixmap] | None = None
        WaveArtStore.instance().updated.connect(self._invalidate)

    def set_mood(self, mood: WaveMood) -> None:
        if mood != self._mood:
            self._mood = mood
            self.update()

    def _invalidate(self) -> None:
        self._cache = None
        self.update()

    def _render(self) -> QPixmap:
        dpr = self.devicePixelRatioF()
        key = (self._mood, dpr)
        if self._cache is not None and self._cache[0] == key:
            return self._cache[1]
        pixmap = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        art = QRectF(self.GLOW, self.GLOW, self.ART, self.ART)
        glow = QRadialGradient(art.center(), self.ART * 0.72)
        glow.setColorAt(0.6, _alpha(mood_color(self._mood), 120))
        glow.setColorAt(1.0, _alpha(mood_color(self._mood), 0))
        painter.fillRect(QRectF(self.rect()), glow)
        path = QPainterPath()
        path.addRoundedRect(art, 30, 30)
        painter.save()
        painter.setClipPath(path)
        paint_wave_art(painter, art, self._mood)
        painter.restore()
        painter.setPen(QPen(QColor(255, 255, 255, 70), 1.2))
        painter.drawPath(path)
        painter.end()
        self._cache = (key, pixmap)
        return pixmap

    def paintEvent(self, event) -> None:
        if self._mood is None:
            return
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self._render())
        painter.end()


class _QueueList(QWidget):
    """Что играет и что дальше в волне: обложка, название, артист."""

    ROW = 52
    COVER = 40

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracks: list[Track] = []
        self._accent = QColor("#7C4DFF")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(0)
        CoverDecoder.instance().ready.connect(self.update)

    def set_tracks(self, tracks: list[Track], accent: QColor) -> None:
        self._tracks = list(tracks)
        self._accent = QColor(accent)
        self.setFixedHeight(self.ROW * len(self._tracks))
        self.update()

    def tracks(self) -> list[Track]:
        return list(self._tracks)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        title_font = _ui_font(13, QFont.Weight.DemiBold)
        artist_font = _ui_font(11)
        for index, track in enumerate(self._tracks):
            top = index * self.ROW
            row = QRectF(0, top + 2, self.width(), self.ROW - 4)
            if index == 0:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(_alpha(self._accent, 46))
                painter.drawRoundedRect(row, 14, 14)
            cover = QRectF(8, top + (self.ROW - self.COVER) / 2, self.COVER, self.COVER)
            paint_rounded_cover(
                painter,
                cover.toRect(),
                label=track.title,
                pixmap=request_track_cover(track, self.COVER),
                source_key=str(track.source),
                radius=10,
            )
            text_left = cover.right() + 12
            text_w = self.width() - text_left - 12
            painter.setFont(title_font)
            painter.setPen(QColor(255, 255, 255, 235 if index == 0 else 190))
            metrics = QFontMetricsF(title_font)
            painter.drawText(
                QRectF(text_left, top + 8, text_w, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(track.title, Qt.TextElideMode.ElideRight, text_w),
            )
            painter.setFont(artist_font)
            painter.setPen(QColor(255, 255, 255, 120))
            metrics = QFontMetricsF(artist_font)
            painter.drawText(
                QRectF(text_left, top + 27, text_w, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                metrics.elidedText(track.author, Qt.TextElideMode.ElideRight, text_w),
            )
        painter.end()


class WavePanel(QFrame):
    """Главное справа от карты: волна крупно, запуск и очередь."""

    play_clicked = Signal()
    shuffle_clicked = Signal()
    reset_clicked = Signal()

    WIDTH = 384

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("wavePanel")
        self.setMinimumHeight(MoodField.MIN_HEIGHT)
        self._color = QColor("#7C4DFF")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.setSpacing(6)
        self._caption = QLabel()
        self._caption.setObjectName("wavePanelCaption")
        layout.addWidget(self._caption)
        self._art = _PanelArt()
        layout.addWidget(self._art, 0, Qt.AlignmentFlag.AlignHCenter)
        self._title = QLabel()
        self._title.setObjectName("wavePanelTitle")
        self._title.setWordWrap(True)
        self._title.setFont(_display_font(26, QFont.Weight.Bold))
        layout.addWidget(self._title)
        self._subtitle = QLabel()
        self._subtitle.setObjectName("wavePanelSubtitle")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)
        layout.addSpacing(10)

        self._play = self._button("▶  Слушать", "waveHeroPlay")
        self._play.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._play.clicked.connect(self.play_clicked.emit)
        layout.addWidget(self._play)
        layout.addSpacing(4)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        self._shuffle = self._button("Встряхнуть", "waveHeroAction")
        self._shuffle.setToolTip("Та же волна, но непривычные треки")
        self._shuffle.clicked.connect(self.shuffle_clicked.emit)
        self._reset = self._button("К привычному", "waveHeroAction")
        self._reset.setToolTip("Вернуть обычную «Мою волну»")
        self._reset.clicked.connect(self.reset_clicked.emit)
        for button in (self._shuffle, self._reset):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self._hint = QLabel(
            "Выберите на карте настроение и занятие — смешаем их в одну волну. "
            "Двойной клик по кружку — сразу играть."
        )
        self._hint.setObjectName("wavePanelHint")
        self._hint.setWordWrap(True)
        layout.addSpacing(8)
        layout.addWidget(self._hint)

        self._queue_caption = QLabel("ДАЛЬШЕ В ВОЛНЕ")
        self._queue_caption.setObjectName("wavePanelCaption")
        layout.addSpacing(10)
        layout.addWidget(self._queue_caption)
        self._queue = _QueueList()
        layout.addWidget(self._queue)
        layout.addStretch(1)

    @staticmethod
    def _button(text: str, name: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName(name)
        button.setText(text)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def set_view(
        self,
        *,
        caption: str,
        mood: WaveMood,
        title: str,
        subtitle: str,
        play_text: str,
        show_reset: bool,
        show_hint: bool,
        busy: bool,
    ) -> None:
        self._color = mood_color(mood)
        self._caption.setText(caption)
        self._art.set_mood(mood)
        self._title.setText(title)
        self._subtitle.setText(subtitle)
        self._subtitle.setVisible(bool(subtitle))
        self._play.setText(play_text)
        self._reset.setVisible(show_reset)
        self._hint.setVisible(show_hint)
        for button in (self._play, self._shuffle, self._reset):
            button.setEnabled(not busy)
        self.update()

    def set_queue(self, tracks: list[Track]) -> None:
        self._queue.set_tracks(tracks, self._color)
        self._queue_caption.setVisible(bool(tracks))

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 28, 28)
        painter.fillPath(path, QColor(9, 10, 17, 236))
        tint = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        tint.setColorAt(0.0, _alpha(self._color, 70))
        tint.setColorAt(0.55, _alpha(self._color, 0))
        painter.fillPath(path, tint)
        painter.setPen(QPen(_alpha(self._color, 80), 1.2))
        painter.drawPath(path)
        painter.end()


def _short(seed: str) -> str:
    node = NODE_BY_SEED.get(seed)
    return node.short if node is not None else seed


class WavePage(QWidget):
    """Страница «Моей волны»: карта настроения слева, главное — справа."""

    toggle_pause_requested = Signal()

    NARROW = 1040
    """Уже этого панель уходит под карту."""
    STAGE_HEIGHT = 560

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
        self._edited = False
        """Пользователь сам собрал рецепт на карте — не перетираем его."""
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

        self._stage = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._stage.setSpacing(18)
        self._field = MoodField()
        self._field.selection_changed.connect(self._on_selection)
        self._field.play_requested.connect(self._on_play)
        self._panel = WavePanel()
        self._panel.setFixedWidth(WavePanel.WIDTH)
        self._panel.play_clicked.connect(self._on_play)
        self._panel.shuffle_clicked.connect(self._on_reshuffle)
        self._panel.reset_clicked.connect(self._on_reset)
        # Карта тянется до высоты панели — без пустот сверху и снизу.
        self._field.setMinimumHeight(self.STAGE_HEIGHT)
        self._panel.setMinimumHeight(self.STAGE_HEIGHT)
        self._stage.addWidget(self._field, 1)
        self._stage.addWidget(self._panel, 0)
        layout.addLayout(self._stage)

        self._sections: list[tuple[HomeSection, _CardFlow]] = []
        self._picks = self._add_section(
            layout, "Подобрано для вас", "Меняется после каждого выбора"
        )
        self._genres = self._add_section(layout, "Жанры")
        self._character = self._add_section(layout, "Характер")
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

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        narrow = self.width() < self.NARROW
        direction = (
            QBoxLayout.Direction.TopToBottom
            if narrow
            else QBoxLayout.Direction.LeftToRight
        )
        if self._stage.direction() != direction:
            self._stage.setDirection(direction)
            if narrow:
                self._panel.setMinimumWidth(0)
                self._panel.setMaximumWidth(16777215)
                self._panel.setMinimumHeight(0)  # под картой — по содержимому
            else:
                self._panel.setFixedWidth(WavePanel.WIDTH)
                self._panel.setMinimumHeight(self.STAGE_HEIGHT)

    # --- состояние ---------------------------------------------------------

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self._sync_state()

    def set_now_playing(self, _track: object = None) -> None:
        self._sync_state()

    def set_eco(self, enabled: bool) -> None:
        self._eco = enabled
        self._field.set_eco(enabled)
        self._sync_state()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._vm.wave_moods and self._bridge is not None:
            schedule(self._vm.refresh_wave_moods(), self._bridge)
        self._sync()

    def recipe(self) -> tuple[str, ...]:
        return tuple(seed for seed in self._field.selection() if seed)

    def recipe_mood(self) -> WaveMood | None:
        """Волна из выбранного на карте: одно настроение/занятие или смесь."""
        seeds = self.recipe()
        if not seeds:
            return None
        if len(seeds) == 1:
            return NODE_BY_SEED[seeds[0]].mood
        # У колеса бывает своё имя для такого сочетания — оно живее нашего.
        for mood in self._vm.wave_moods:
            if set(mood.seeds) == set(seeds):
                return mood
        first = NODE_BY_SEED[seeds[0]].mood
        return WaveMood(
            id=",".join(seeds),
            name=" + ".join(_short(s) for s in seeds),
            seeds=seeds,
            description="Настроение и занятие в одной волне",
            color=first.color,
        )

    def _sync(self) -> None:
        picks = [
            m
            for m in self._vm.wave_moods
            if not m.is_control
            and mood_kind(m) not in ("character", "mood", "activity")
        ]
        current = [card.mood for card in self._picks.cards()]
        if picks != current:
            self._picks.set_cards(self._make_cards(picks))
        self._sections[0][0].setVisible(bool(picks))
        if not self._edited:
            self._select_from(self._vm.active_wave_seeds)
        self._sync_state()

    def _select_from(self, seeds: tuple[str, ...]) -> None:
        mood = next(
            (s for s in seeds if s.startswith("mood:") and s in NODE_BY_SEED), None
        )
        act = next(
            (s for s in seeds if s.startswith("activity:") and s in NODE_BY_SEED), None
        )
        self._field.set_selection(mood, act)

    def _sync_state(self) -> None:
        current = self._vm.wave_is_current
        busy = self._vm.wave_mood_busy
        active = self._vm.active_wave_mood
        active_seeds = self._vm.active_wave_seeds
        recipe = self.recipe()
        is_default = active_seeds == ("user:onyourwave",)
        self._field.set_active(active_seeds if current else (), playing=self._playing)

        preview = bool(recipe) and (set(recipe) != set(active_seeds) or not current)
        if preview:
            mood = self.recipe_mood()
            assert mood is not None
            subtitle = self._subtitle(mood)
            self._panel.set_view(
                caption="СОБРАНО НА КАРТЕ",
                mood=mood,
                title=mood.name,
                subtitle=subtitle,
                play_text="▶  Включить",
                show_reset=current and not is_default,
                show_hint=False,
                busy=busy,
            )
        else:
            state = "idle"
            if current:
                state = "playing" if self._playing else "paused"
            self._panel.set_view(
                caption={
                    "playing": "СЕЙЧАС В ВОЛНЕ",
                    "paused": "ВОЛНА НА ПАУЗЕ",
                }.get(state, "МОЯ ВОЛНА"),
                mood=active,
                title=active.name,
                subtitle=self._subtitle(active),
                play_text={"playing": "❚❚  Пауза", "paused": "▶  Продолжить"}.get(
                    state, "▶  Слушать"
                ),
                show_reset=not is_default,
                show_hint=not recipe and not current,
                busy=busy,
            )
        self._panel.set_queue(self._vm.wave_queue(3) if current else [])

        for _, flow in self._sections:
            for card in flow.cards():
                is_active = current and card.mood.seeds == active_seeds
                card.set_active(is_active, animate=self._playing and not self._eco)
                card.setEnabled(not busy)

    @staticmethod
    def _subtitle(mood: WaveMood) -> str:
        """Смесь с карты — «Спокойно + Работа», иначе описание волны."""
        if len(mood.seeds) > 1 and all(s in NODE_BY_SEED for s in mood.seeds):
            return " + ".join(_short(s) for s in mood.seeds)
        return mood.description or "Поток треков под это настроение"

    # --- действия ------------------------------------------------------------

    def _on_selection(self, _mood: object, _activity: object) -> None:
        self._edited = True
        self._sync_state()

    def _start(self, mood: WaveMood) -> None:
        if self._bridge is None:
            return
        self._edited = False
        schedule(self._vm.play_wave_mood(mood), self._bridge)

    def _on_mood(self, mood: WaveMood) -> None:
        if self._bridge is None:
            return
        if self._vm.wave_is_current and mood.seeds == self._vm.active_wave_seeds:
            self.toggle_pause_requested.emit()
            return
        self._start(mood)

    def _on_play(self) -> None:
        if self._bridge is None:
            return
        recipe = self.recipe_mood()
        current = self._vm.wave_is_current
        if recipe is not None and (
            not current or set(recipe.seeds) != set(self._vm.active_wave_seeds)
        ):
            self._start(recipe)
            return
        if current:
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
        self._start(mood)

    def _on_reset(self) -> None:
        mood = self._control("user:onyourwave") or DEFAULT_WAVE_MOOD
        self._field.set_selection(None, None)
        self._start(mood)

    def sizeHint(self) -> QSize:
        return QSize(900, 700)
