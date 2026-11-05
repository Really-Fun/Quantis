"""Текст песни в правой панели.

Синхронный текст (LRC): текущая строка ярче остальных и держится в верхней
трети, клик по строке — перемотка к ней. Несинхронный — просто текст с
прокруткой колесом. Колесо на синхронном тексте на несколько секунд
выключает автопрокрутку, чтобы можно было дочитать.
"""

from __future__ import annotations

from time import monotonic

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPaintEvent,
)
from PySide6.QtWidgets import QApplication, QWidget

from quantis.services.lyrics import Lyrics
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor

_PAD_X = 8
_LINE_GAP = 14
_FADE = 36.0
"""Высота затухания строк у верхнего и нижнего края, px."""
_FREE_SCROLL_S = 4.0
"""Сколько секунд после прокрутки колесом текст не ездит сам."""


class LyricsView(QWidget):
    seek_requested = Signal(int)
    """Клик по строке синхронного текста — позиция в мс."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("lyricsView")
        self.setMouseTracking(True)
        self._lyrics = Lyrics()
        self._state = "empty"
        """empty — нет трека, loading, ready, missing — текста нет."""
        self._current = -1
        self._hover = -1
        self._scroll = 0.0
        self._free_until = 0.0
        self._layout_w = -1
        self._rects: list[QRectF] = []
        self._content_h = 0.0
        self._anim = QPropertyAnimation(self, b"scrollY", self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        UiPreferences().theme_changed.connect(self._relayout)

    # ----------------------------------------------------------- scroll prop

    def _get_scroll(self) -> float:
        return self._scroll

    def _set_scroll(self, value: float) -> None:
        self._scroll = value
        self.update()

    scrollY = Property(float, _get_scroll, _set_scroll)

    # ------------------------------------------------------------------ data

    def set_loading(self) -> None:
        self._set(Lyrics(), "loading")

    def set_empty(self) -> None:
        self._set(Lyrics(), "empty")

    def set_lyrics(self, lyrics: Lyrics) -> None:
        self._set(lyrics, "ready" if lyrics.lines else "missing")

    def _set(self, lyrics: Lyrics, state: str) -> None:
        self._lyrics = lyrics
        self._state = state
        self._current = -1
        self._hover = -1
        self._anim.stop()
        self._scroll = 0.0
        self._free_until = 0.0
        self._relayout()

    @property
    def state(self) -> str:
        return self._state

    @property
    def current_line(self) -> int:
        return self._current

    def set_position(self, position_ms: int) -> None:
        index = self._lyrics.line_at(position_ms)
        if index == self._current:
            return
        self._current = index
        if monotonic() >= self._free_until:
            self._follow(animate=True)
        self.update()

    # --------------------------------------------------------------- layout

    def _font(self) -> QFont:
        font = QFont(QApplication.font())
        font.setPixelSize(19 if self._lyrics.synced else 15)
        font.setWeight(
            QFont.Weight.Bold if self._lyrics.synced else QFont.Weight.Medium
        )
        return font

    def _relayout(self, *_: object) -> None:
        width = max(40, self.width() - 2 * _PAD_X)
        metrics = QFontMetrics(self._font())
        gap = _LINE_GAP if self._lyrics.synced else 6
        y = 8.0
        self._rects = []
        for line in self._lyrics.lines:
            text = line.text or "♪"
            bounds = metrics.boundingRect(
                0, 0, width, 10_000, int(Qt.TextFlag.TextWordWrap), text
            )
            rect = QRectF(_PAD_X, y, width, bounds.height())
            self._rects.append(rect)
            y += bounds.height() + gap
        self._content_h = y + self.height() * 0.6  # последнюю строку можно поднять
        self._layout_w = self.width()
        self._follow(animate=False)
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self.width() != self._layout_w:
            self._relayout()

    def _max_scroll(self) -> float:
        return max(0.0, self._content_h - self.height())

    def _follow(self, *, animate: bool) -> None:
        if not self._lyrics.synced or not (0 <= self._current < len(self._rects)):
            return
        target = self._rects[self._current].top() - self.height() * 0.3
        target = min(max(0.0, target), self._max_scroll())
        if not animate:
            self._anim.stop()
            self._scroll = target
            return
        self._anim.stop()
        self._anim.setStartValue(self._scroll)
        self._anim.setEndValue(target)
        self._anim.start()

    # ---------------------------------------------------------------- input

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._state != "ready":
            return
        self._anim.stop()
        delta = event.angleDelta().y()
        self._scroll = min(max(0.0, self._scroll - delta * 0.6), self._max_scroll())
        self._free_until = monotonic() + _FREE_SCROLL_S
        self.update()
        event.accept()

    def _line_at(self, pos) -> int:
        if not self._lyrics.synced:
            return -1
        y = pos.y() + self._scroll
        for index, rect in enumerate(self._rects):
            if rect.top() - _LINE_GAP / 2 <= y <= rect.bottom() + _LINE_GAP / 2:
                return index
        return -1

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        hover = self._line_at(event.position())
        self.setCursor(
            Qt.CursorShape.PointingHandCursor
            if hover >= 0
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
        index = self._line_at(event.position())
        if index >= 0:
            self._free_until = 0.0
            self.seek_requested.emit(self._lyrics.lines[index].t)

    # ---------------------------------------------------------------- paint

    def paintEvent(self, event: QPaintEvent) -> None:
        colors = UiPreferences().theme.colors
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        if self._state != "ready":
            self._paint_message(painter, colors)
            painter.end()
            return
        plain = qcolor(colors.text)
        font = self._font()
        painter.setFont(font)
        flags = int(Qt.TextFlag.TextWordWrap)
        painter.translate(0, -self._scroll)
        top, bottom = self._scroll - 40, self._scroll + self.height() + 40
        for index, (line, rect) in enumerate(
            zip(self._lyrics.lines, self._rects, strict=True)
        ):
            if rect.bottom() < top or rect.top() > bottom:
                continue
            color = qcolor(colors.text)
            if self._lyrics.synced:
                if index == self._current:
                    alpha = 255
                elif index == self._hover:
                    alpha = 190
                elif index < self._current:
                    alpha = 80
                else:
                    alpha = 120
                color.setAlpha(round(color.alpha() * alpha / 255))
            else:
                color = QColor(plain)
            # у краёв строки гаснут, а не обрезаются о вкладки и подпись
            on_screen = rect.center().y() - self._scroll
            edge = min(on_screen, self.height() - 24 - on_screen)
            if edge < _FADE:
                fade = max(0.0, edge) / _FADE
                color.setAlpha(round(color.alpha() * fade))
            painter.setPen(color)
            painter.drawText(rect, flags, line.text or "♪")
        painter.resetTransform()
        if self._lyrics.source:
            small = QFont(QApplication.font())
            small.setPixelSize(11)
            painter.setFont(small)
            painter.setPen(qcolor(colors.text_meta))
            painter.drawText(
                QRectF(_PAD_X, self.height() - 18, self.width() - 2 * _PAD_X, 16),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                f"Текст: {self._lyrics.source}",
            )
        painter.end()

    def _paint_message(self, painter: QPainter, colors) -> None:
        title, hint = {
            "loading": ("Ищем текст…", ""),
            "missing": (
                "Текста не нашлось",
                "Ни у Яндекс Музыки, ни в базе LRCLIB нет слов к этому треку.",
            ),
        }.get(self._state, ("Ничего не играет", "Включи трек — здесь будут слова."))
        rect = QRectF(_PAD_X, 0, self.width() - 2 * _PAD_X, self.height() * 0.7)
        head = QFont(QApplication.font())
        head.setPixelSize(15)
        head.setWeight(QFont.Weight.Bold)
        painter.setFont(head)
        painter.setPen(qcolor(colors.text))
        center = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        painter.drawText(rect.adjusted(0, 0, 0, -24), center, title)
        if hint:
            small = QFont(QApplication.font())
            small.setPixelSize(12)
            painter.setFont(small)
            painter.setPen(qcolor(colors.text_dim))
            painter.drawText(
                rect.adjusted(16, 28, -16, 28),
                center | int(Qt.TextFlag.TextWordWrap),
                hint,
            )
