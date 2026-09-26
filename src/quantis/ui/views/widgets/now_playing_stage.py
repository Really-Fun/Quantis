"""Главная: сцена «Сейчас играет» и стеклянная панель «Дальше».

Сцена: большая обложка, из-под неё выглядывает пластинка (крутится только во
время воспроизведения), название трека шрифтом display темы, артист, спектр и
чип источника. Три состояния: играет / можно продолжить последний трек /
первый запуск («Выбери трек»).

Производительность: всё статичное — ореол, обложка с тенью, блик пластинки —
запекается в пиксмапы; каждый кадр рисуется только поворот пластинки и спектр.
Анимация идёт ~30 к/с, только пока трек играет, окно не в эко и сцена видна.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from time import monotonic
from typing import Literal

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)

from quantis.models import Track
from quantis.ui.cover_accent import CoverPalette
from quantis.ui.live_palette import LivePalette
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import ThemeSpec, qcolor
from quantis.ui.views.widgets.cover_art import load_track_cover
from quantis.ui.views.widgets.elided_label import ElidedLabel
from quantis.ui.views.widgets.glass import paint_glass
from quantis.ui.views.widgets.source_badge import source_badge_color

StageMode = Literal["playing", "resume", "empty"]

FRAME_MS = 33
SOURCE_NAMES = {"youtube": "YouTube", "yandex": "Яндекс", "soundcloud": "SoundCloud"}


def source_name(source: str | None) -> str:
    key = str(source or "").lower()
    return SOURCE_NAMES.get(key, key.capitalize() or "Файл")


def cached(
    owner: object,
    attr: str,
    key: object,
    size: QSize,
    dpr: float,
    paint: Callable[[QPainter], None],
) -> QPixmap:
    """Рисует ``paint`` в пиксмап и держит его, пока не поменяется ``key``:
    статичное не перерисовывается на каждом кадре пластинки и спектра."""
    full = (key, size.width(), size.height(), dpr)
    hit: tuple[object, QPixmap] | None = getattr(owner, attr, None)
    if hit is not None and hit[0] == full:
        return hit[1]
    pixmap = QPixmap(max(1, int(size.width() * dpr)), max(1, int(size.height() * dpr)))
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    paint(painter)
    painter.end()
    setattr(owner, attr, (full, pixmap))
    return pixmap


def _alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out


def _theme() -> ThemeSpec:
    return UiPreferences().theme


class Spectrum(QWidget):
    """Спектр. Пока нет FFT плеера — анимация по синусам, как в демо;
    на паузе и в эко стоит."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.t = 1.35
        self._palette = LivePalette.instance().current

    def set_palette(self, palette: CoverPalette) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        # кадры фона перерисовывают спектр и между его тиками — берём из кэша
        key = (self.t, self._palette.accent.rgba(), self._palette.accent2.rgba())
        pixmap = cached(
            self, "_pm", key, self.size(), self.devicePixelRatioF(), self._paint_bars
        )
        painter = QPainter(self)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

    def _paint_bars(self, painter: QPainter) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        w, h = self.width(), self.height()
        step, bar = 7, 3.6
        n = int(w // step)
        base = h * 0.74
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0, self._palette.accent)
        gradient.setColorAt(1, self._palette.accent2)
        painter.setBrush(QBrush(gradient))
        t = self.t
        for i in range(n):
            f = i / max(1, n - 1)
            env = (
                0.3
                + 0.7 * math.exp(-((f - 0.22) ** 2) / 0.07)
                + 0.25 * math.exp(-((f - 0.7) ** 2) / 0.02)
            )
            v = abs(math.sin(t * 2.3 + i * 0.42) * math.cos(t * 1.1 + i * 0.17))
            v = 0.12 + 0.88 * v * min(1.0, env) * (
                0.78 + 0.22 * math.sin(t * 7 + i * 1.7)
            )
            bh = max(3.0, base * v)
            x = i * step
            painter.setOpacity(1.0)
            painter.drawRoundedRect(QRectF(x, base - bh, bar, bh), bar / 2, bar / 2)
            painter.setOpacity(0.16)
            painter.drawRoundedRect(
                QRectF(x, base + 3, bar, bh * 0.3), bar / 2, bar / 2
            )


class SourceChip(QWidget):
    """Чип источника трека. Пока у ``Track`` один источник — один чип;
    «где ещё есть этот трек» появится вместе с кросс-поиском."""

    H = 32

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(self.H)
        self._source = ""

    def set_source(self, source: str) -> None:
        self._source = source
        font = self._font()
        width = QFontMetrics(font).horizontalAdvance(source_name(source))
        self.setFixedWidth(26 + width + 16)
        self.update()

    def _font(self) -> QFont:
        font = QFont(QApplication.font())
        font.setPixelSize(13)
        font.setWeight(QFont.Weight.DemiBold)
        return font

    def paintEvent(self, event: QPaintEvent) -> None:
        if not self._source:
            return
        theme = _theme()
        color = source_badge_color(self._source)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setBrush(_alpha(color, 56))
        painter.setPen(QPen(_alpha(color, 190), 1))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        center = QPointF(rect.x() + 16, rect.center().y())
        glow = QRadialGradient(center, 8)
        glow.setColorAt(0, _alpha(color, 150))
        glow.setColorAt(1, _alpha(color, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(center, 8, 8)
        painter.setBrush(color)
        painter.drawEllipse(center, 3.5, 3.5)
        painter.setFont(self._font())
        painter.setPen(qcolor(theme.colors.text))
        painter.drawText(
            QRectF(rect.x() + 26, 0, rect.width() - 26, self.H),
            Qt.AlignmentFlag.AlignVCenter,
            source_name(self._source),
        )
        painter.end()


class NowPlayingStage(QWidget):
    """Сцена вверху главной. Размер задаёт главная (``set_cover_size``): от
    обложки считаются высота, пластинка и отступ текста — на маленьком окне
    (Windows 150 %) сцена ужимается, а не выталкивает «Дальше» за край."""

    H, COVER, OUT = 316, 292, 122
    """Полный размер; ``H - COVER`` — поля сверху и снизу."""
    MIN_COVER = 200
    COMPACT_BELOW = 250
    """Обложка меньше — заголовок мельче (qss ``[compact="true"]``)."""
    resume_requested = Signal()
    wave_requested = Signal()
    search_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("nowPlayingStage")
        self._cover_px, self._out, self._h = self.COVER, self.OUT, self.H
        self._compact = False
        self.setFixedHeight(self._h)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._track: Track | None = None
        self._mode: StageMode = "empty"
        self._playing = False
        self._eco = False
        self._greeting = "Добро пожаловать"
        self._angle = 24.0
        self._palette = LivePalette.instance().current
        self._cover: QPixmap | None = None
        self._grooves = self._make_grooves(268)
        self._clock = monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(FRAME_MS)
        self._timer.timeout.connect(self._tick)

        row = QHBoxLayout(self)
        self._row = row
        row.setContentsMargins(self._text_left(), 6, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(0)
        self._kicker = QLabel()
        self._kicker.setObjectName("stageKicker")
        # длинный текст режется, а не раздвигает сцену шире окна
        self._kicker.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        col.addWidget(self._kicker)
        self._gaps = [self._gap(col, 8)]
        self._title = ElidedLabel(max_lines=2)
        self._title.setObjectName("stageTitle")
        self._title.setMaximumHeight(112)
        col.addWidget(self._title)
        self._gaps.append(self._gap(col, 8))
        self._artist = ElidedLabel(max_lines=2)
        self._artist.setObjectName("stageArtist")
        col.addWidget(self._artist)
        col.addStretch(1)
        self._spectrum = Spectrum()
        col.addWidget(self._spectrum)
        self._gaps.append(self._gap(col, 12))
        self._chip_label = QLabel("Источник")
        self._chip_label.setObjectName("stageChipLabel")
        col.addWidget(self._chip_label)
        col.addSpacing(8)
        actions = QHBoxLayout()
        actions.setSpacing(10)
        self._chip = SourceChip()
        actions.addWidget(self._chip)
        self._resume_btn = self._pill("▶  Продолжить", self.resume_requested.emit)
        self._wave_btn = self._pill("Моя волна", self.wave_requested.emit)
        self._search_btn = self._pill("Найти трек", self.search_requested.emit)
        for button in (self._resume_btn, self._wave_btn, self._search_btn):
            actions.addWidget(button)
        actions.addStretch(1)
        col.addLayout(actions)
        col.addSpacing(8)
        row.addLayout(col, 1)

        LivePalette.instance().palette_changed.connect(self._on_palette)
        self._apply_mode()

    @staticmethod
    def _gap(col: QVBoxLayout, size: int) -> tuple[QSpacerItem, int]:
        col.addSpacing(size)
        spacer = col.itemAt(col.count() - 1).spacerItem()
        assert spacer is not None
        return spacer, size

    # --- размер ----------------------------------------------------------

    def _text_left(self) -> int:
        return self._cover_px + self._out + round(40 * self._cover_px / self.COVER)

    @property
    def cover_size(self) -> int:
        return self._cover_px

    @classmethod
    def height_for(cls, cover: int) -> int:
        return cover + cls.H - cls.COVER

    def set_cover_size(self, cover: int) -> None:
        """Обложка ``cover`` px (в пределах MIN_COVER…COVER), остальное — от неё."""
        cover = max(self.MIN_COVER, min(self.COVER, int(cover)))
        if cover == self._cover_px:
            return
        self._cover_px = cover
        self._out = round(self.OUT * cover / self.COVER)
        self._h = self.height_for(cover)
        self.setFixedHeight(self._h)
        self._grooves = self._make_grooves(round(268 * cover / self.COVER))
        self._row.setContentsMargins(self._text_left(), 6, 0, 0)
        compact = cover < self.COMPACT_BELOW
        self._compact = compact
        # на низкой сцене колонке текста не хватает высоты: спектр ниже,
        # подпись «Источник» лишняя — чип и так говорит сам за себя
        self._spectrum.setFixedHeight(round(58 * max(0.62, self._k())))
        self._chip_label.setVisible(self._has_track() and not compact)
        for spacer, size in self._gaps:
            spacer.changeSize(0, size // 2 if compact else size)
        self._row.invalidate()
        if self._title.property("compact") != compact:
            self._title.setProperty("compact", compact)
            self._title.style().unpolish(self._title)
            self._title.style().polish(self._title)
        self.update()

    def _pill(self, text: str, slot: Callable[[], None]) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("stagePill")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(slot)
        return button

    # --- состояние -------------------------------------------------------

    @property
    def mode(self) -> StageMode:
        return self._mode

    def set_track(self, track: Track | None, *, mode: StageMode) -> None:
        """Трек сцены: играющий (``playing``), последний из истории (``resume``)
        или ничего (``empty``)."""
        if track is None:
            mode = "empty"
        changed = track is not self._track or mode != self._mode
        self._track, self._mode = track, mode
        if not changed:
            return
        # грузим в полный размер: сцена может вырасти, рисуем в прямоугольник
        self._cover = load_track_cover(track, self.COVER) if track is not None else None
        self._apply_mode()
        self.update()

    def set_greeting(self, greeting: str) -> None:
        self._greeting = greeting
        if self._mode == "empty":
            self._kicker.setText(greeting)

    def set_playing(self, playing: bool) -> None:
        self._playing = playing
        self._sync_timer()

    def set_eco(self, enabled: bool) -> None:
        self._eco = enabled
        self._sync_timer()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def _apply_mode(self) -> None:
        track, mode = self._track, self._mode
        if mode == "empty" or track is None:
            self._kicker.setText(self._greeting)
            self._title.setText("Выбери трек")
            self._artist.set_max_lines(2)
            self._artist.setText("Найди что-нибудь в поиске или включи «Мою волну»")
        else:
            self._kicker.setText(
                "Сейчас играет" if mode == "playing" else "Продолжить слушать"
            )
            self._title.setText(track.title)
            self._artist.set_max_lines(1)  # под ним спектр — высота на счету
            self._artist.setText(track.author)
            self._chip.set_source(str(track.source))
        has_track = self._has_track()
        self._spectrum.setVisible(has_track)
        self._chip_label.setVisible(has_track and not self._compact)
        self._chip.setVisible(has_track)
        self._resume_btn.setVisible(mode == "resume")
        self._wave_btn.setVisible(mode == "empty")
        self._search_btn.setVisible(mode == "empty")
        self._sync_timer()

    def _has_track(self) -> bool:
        return self._mode != "empty" and self._track is not None

    def _sync_timer(self) -> None:
        run = (
            self._mode == "playing"
            and self._playing
            and not self._eco
            and self.isVisible()
        )
        if run and not self._timer.isActive():
            self._clock = monotonic()
            self._timer.start()
        elif not run and self._timer.isActive():
            self._timer.stop()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._sync_timer()

    def hideEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().hideEvent(event)
        self._sync_timer()

    def _on_palette(self, palette: CoverPalette) -> None:
        self._palette = palette
        self._spectrum.set_palette(palette)
        self.update(self._art_rect())

    def _tick(self) -> None:
        now = monotonic()
        dt, self._clock = min(0.1, now - self._clock), now
        self._spectrum.t += dt
        self._spectrum.update()
        self._angle = (self._angle + dt * 200) % 360  # ~33 об/мин
        self.update(self._art_rect())

    # --- рисование -------------------------------------------------------

    def _art_rect(self) -> QRect:
        return QRect(0, 0, self._cover_px + self._out + 4, self._h)

    def _k(self) -> float:
        """Масштаб сцены относительно полного размера."""
        return self._cover_px / self.COVER

    def _geom(self) -> tuple[QRectF, float, QPointF]:
        c = self._cover_px
        cover = QRectF(0, (self._h - c) / 2, c, c)
        d = self._grooves.width() / self._grooves.devicePixelRatio()
        return cover, d, QPointF(cover.right() + self._out - d / 2, cover.center().y())

    @staticmethod
    def _make_grooves(d: int) -> QPixmap:
        dpr = 2
        pixmap = QPixmap(d * dpr, d * dpr)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(dpr)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center, radius = QPointF(d / 2, d / 2), d / 2
        body = QRadialGradient(center, radius)
        body.setColorAt(0, QColor("#1B1826"))
        body.setColorAt(0.96, QColor("#0B0A10"))
        body.setColorAt(1, QColor("#26222F"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(body)
        painter.drawEllipse(center, radius, radius)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        rnd = random.Random(5)
        r = radius * 0.36
        while r < radius * 0.95:
            painter.setPen(QPen(QColor(255, 255, 255, rnd.randint(5, 14)), 0.7))
            painter.drawEllipse(center, r, r)
            r += 2.2 + rnd.random() * 1.4
        painter.end()
        return pixmap

    def paintEvent(self, event: QPaintEvent) -> None:
        area = QSize(self._cover_px + self._out + 60, self._h)
        dpr = self.devicePixelRatioF()
        accent = self._palette.accent
        painter = QPainter(self)
        painter.drawPixmap(
            0, 0, cached(self, "_pm_back", accent.rgba(), area, dpr, self._paint_back)
        )
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        cover, d, center = self._geom()
        painter.save()
        painter.translate(center)
        painter.rotate(self._angle)
        painter.drawPixmap(QPointF(-d / 2, -d / 2), self._grooves)
        k = self._k()
        label = QRadialGradient(QPointF(0, 0), 46 * k)
        label.setColorAt(0, self._palette.accent2)
        label.setColorAt(1, accent)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(label)
        painter.drawEllipse(QPointF(0, 0), 44 * k, 44 * k)
        painter.setBrush(QColor(255, 255, 255, 200))
        painter.drawEllipse(QPointF(0, -26 * k), 3, 3)
        painter.setBrush(qcolor(_theme().colors.bg))
        painter.drawEllipse(QPointF(0, 0), 4, 4)
        painter.restore()
        key = (self._cover.cacheKey() if self._cover else 0, _theme().id)
        painter.drawPixmap(
            0, 0, cached(self, "_pm_front", key, area, dpr, self._paint_front)
        )
        painter.end()

    def _paint_back(self, painter: QPainter) -> None:
        cover, _, _ = self._geom()
        k = self._k()
        r = 150 * k
        center = QPointF(cover.center().x() + 60 * k, cover.center().y())
        halo = QRadialGradient(center, r)
        accent = self._palette.accent
        halo.setColorAt(0, _alpha(accent, 110))
        halo.setColorAt(0.6, _alpha(accent, 35))
        halo.setColorAt(1, _alpha(accent, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(center, r, r)

    def _paint_front(self, painter: QPainter) -> None:
        cover, d, center = self._geom()
        painter.setPen(Qt.PenStyle.NoPen)
        sheen = QConicalGradient(center, 40)
        for pos, a in (
            (0, 0),
            (0.06, 26),
            (0.13, 0),
            (0.5, 0),
            (0.56, 18),
            (0.63, 0),
            (1, 0),
        ):
            sheen.setColorAt(pos, QColor(255, 255, 255, a))
        painter.setBrush(sheen)
        painter.drawEllipse(center, d / 2 - 2, d / 2 - 2)
        # обложка с тенью — рисованной, без QGraphicsDropShadowEffect;
        # на светлой теме тень мягче, иначе под обложкой серая плита
        soft = 0.45 if _theme().is_light else 1.0
        for i, a in enumerate((70, 40, 20)):
            painter.setBrush(QColor(0, 0, 0, int(a * soft)))
            painter.drawRoundedRect(
                cover.adjusted(-2 - i * 3, 4 + i * 2, 2 + i * 3, 10 + i * 5), 24, 24
            )
        path = QPainterPath()
        path.addRoundedRect(cover, 22, 22)
        if self._cover is not None and not self._cover.isNull():
            painter.save()
            painter.setClipPath(path)
            painter.drawPixmap(cover, self._cover, QRectF(self._cover.rect()))
            painter.restore()
        else:
            self._paint_placeholder(painter, cover, path)
        shine = QLinearGradient(cover.topLeft(), cover.bottomRight())
        shine.setColorAt(0, QColor(255, 255, 255, 34))
        shine.setColorAt(0.45, QColor(255, 255, 255, 0))
        painter.fillPath(path, shine)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        inner = QPainterPath()
        inner.addRoundedRect(cover.adjusted(0.5, 0.5, -0.5, -0.5), 22, 22)
        painter.drawPath(inner)

    def _paint_placeholder(
        self, painter: QPainter, cover: QRectF, path: QPainterPath
    ) -> None:
        """Нет обложки (или ничего не играет): мягкий градиент палитры и нота."""
        palette = self._palette
        gradient = QLinearGradient(cover.topLeft(), cover.bottomRight())
        gradient.setColorAt(0, _alpha(palette.accent, 150))
        gradient.setColorAt(1, _alpha(palette.deep, 230))
        painter.fillPath(path, gradient)
        font = QFont(QApplication.font())
        font.setPixelSize(round(96 * self._k()))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255, 190))
        painter.drawText(cover, Qt.AlignmentFlag.AlignCenter, "♪")


@dataclass(frozen=True)
class UpNextItem:
    track: Track
    index: int
    """Позиция в текущем плейлисте — по клику играем её."""


def upcoming(
    tracks: Sequence[Track], current: Track | None, current_index: int, count: int = 4
) -> list[UpNextItem]:
    """Следующие ``count`` треков очереди после текущего (по кругу, как играет
    плеер), без повторов текущего."""
    n = len(tracks)
    if n <= 1:
        return []
    start = current_index
    if current is not None and current in tracks:
        start = list(tracks).index(current)
    items: list[UpNextItem] = []
    for k in range(1, min(count, n - 1) + 1):
        index = (start + k) % n
        items.append(UpNextItem(tracks[index], index))
    return items


class UpNextPanel(QWidget):
    """Стеклянная панель «Дальше»: до 4 треков очереди — сколько влезает.

    Размер задаёт главная: рядом со сценой — её высоты, под сценой (узкое
    окно) — во всю ширину, треки в две колонки."""

    W, MIN_W = 304, 264
    ROW = 60
    TOP = 62
    """Шапка «Дальше» / «Вся очередь»."""
    track_activated = Signal(int)
    """Индекс трека в текущем плейлисте."""
    queue_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("upNextPanel")
        self.setFixedSize(self.W, NowPlayingStage.H)
        self.setMouseTracking(True)
        self._items: list[UpNextItem] = []
        self._covers: list[QPixmap | None] = []
        self._palette = LivePalette.instance().current
        self._hover = -1
        LivePalette.instance().palette_changed.connect(self._on_palette)

    @classmethod
    def height_for(cls, rows: int) -> int:
        return cls.TOP + rows * cls.ROW + 8

    def columns(self) -> int:
        return 2 if self.width() >= 560 else 1

    def visible_count(self) -> int:
        rows = max(1, (self.height() - self.TOP - 8) // self.ROW)
        return min(len(self._items), rows * self.columns())

    def _item_rect(self, index: int) -> QRectF:
        """Строка трека ``index`` (с подсветкой): колонки сверху вниз."""
        cols = self.columns()
        count = self.visible_count()
        rows = max(1, -(-count // cols))
        col, row = divmod(index, rows)
        col_w = (self.width() - 24) / cols
        return QRectF(12 + col * col_w, self.TOP - 6 + row * self.ROW, col_w, 56)

    def set_items(self, items: list[UpNextItem]) -> None:
        keys = [(i.track, i.index) for i in items]
        if keys == [(i.track, i.index) for i in self._items]:
            return
        self._items = items
        self._covers = [load_track_cover(i.track, 44) for i in items]
        self.update()

    def items(self) -> list[UpNextItem]:
        return list(self._items)

    def _on_palette(self, palette: CoverPalette) -> None:
        self._palette = palette
        if not LivePalette.instance().is_animating():
            self.update()  # ссылка «Вся очередь» цветом акцента — без покадровой анимации

    def _row_at(self, pos: QPointF) -> int:
        for index in range(self.visible_count()):
            if self._item_rect(index).contains(pos):
                return index
        return -1

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        hover = self._row_at(event.position())
        on_link = bool(self._items) and self._link_rect().contains(event.position())
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if hover >= 0 or on_link
            else Qt.CursorShape.ArrowCursor
        )
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._items and self._link_rect().contains(event.position()):
            self.queue_requested.emit()
            return
        row = self._row_at(event.position())
        if row >= 0:
            self.track_activated.emit(self._items[row].index)

    def _link_rect(self) -> QRectF:
        return QRectF(self.width() - 160, 20, 138, 24)

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = _theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, 22, 22)
        if not paint_glass(self, painter, path):
            painter.fillPath(path, qcolor(theme.colors.surface))
        painter.setPen(QPen(_alpha(qcolor(theme.colors.ink_rgb), 26), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        self._paint_content(painter, theme, rect)
        painter.end()

    def _paint_content(self, painter: QPainter, theme: ThemeSpec, rect: QRectF) -> None:
        colors = theme.colors
        text, dim = qcolor(colors.text), qcolor(colors.text_dim)
        title_font = QFont(QApplication.font())
        title_font.setFamilies(list(theme.fonts.families("display")))
        title_font.setPixelSize(15)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(text)
        painter.drawText(
            QRectF(22, 20, 200, 24), Qt.AlignmentFlag.AlignVCenter, "Дальше"
        )
        small = QFont(QApplication.font())
        small.setPixelSize(12)
        small.setWeight(QFont.Weight.DemiBold)
        painter.setFont(small)
        if self._items:  # пустую очередь открывать незачем
            painter.setPen(self._palette.accent)
            painter.drawText(
                self._link_rect(),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "Вся очередь",
            )
        if not self._items:
            painter.setPen(dim)
            painter.drawText(
                QRectF(22, self.TOP, rect.width() - 44, 60),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                "Очередь пуста",
            )
            return
        name_font = QFont(QApplication.font())
        name_font.setPixelSize(14)
        name_font.setWeight(QFont.Weight.DemiBold)
        meta_font = QFont(QApplication.font())
        meta_font.setPixelSize(12)
        count = self.visible_count()
        for row, (item, cover) in enumerate(
            zip(self._items[:count], self._covers[:count], strict=True)
        ):
            cell = self._item_rect(row)
            if row == self._hover:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(_alpha(qcolor(colors.ink_rgb), 14))
                painter.drawRoundedRect(cell, 12, 12)
            x, y, right = cell.x() + 10, cell.y() + 6, cell.right() - 10
            box = QRectF(x, y, 44, 44)
            clip = QPainterPath()
            clip.addRoundedRect(box, 9, 9)
            if cover is not None and not cover.isNull():
                painter.save()
                painter.setClipPath(clip)
                painter.drawPixmap(box, cover, QRectF(cover.rect()))
                painter.restore()
            else:
                gradient = QLinearGradient(box.topLeft(), box.bottomRight())
                gradient.setColorAt(0, self._palette.accent)
                gradient.setColorAt(1, self._palette.deep)
                painter.fillPath(clip, gradient)
            text_x = x + 56
            text_w = right - text_x - 62
            painter.setFont(name_font)
            painter.setPen(text)
            painter.drawText(
                QRectF(text_x, y + 2, text_w, 20),
                Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(name_font).elidedText(
                    item.track.title, Qt.TextElideMode.ElideRight, int(text_w)
                ),
            )
            painter.setFont(meta_font)
            painter.setPen(dim)
            painter.drawText(
                QRectF(text_x, y + 22, text_w, 20),
                Qt.AlignmentFlag.AlignVCenter,
                QFontMetrics(meta_font).elidedText(
                    item.track.author, Qt.TextElideMode.ElideRight, int(text_w)
                ),
            )
            dot = QPointF(right - 48, y + 22)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(source_badge_color(str(item.track.source)))
            painter.drawEllipse(dot, 3.2, 3.2)
            duration = int(getattr(item.track, "duration_ms", 0) or 0) // 1000
            if duration > 0:
                painter.setPen(dim)
                painter.drawText(
                    QRectF(right - 40, y, 40, 44),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    f"{duration // 60}:{duration % 60:02d}",
                )
