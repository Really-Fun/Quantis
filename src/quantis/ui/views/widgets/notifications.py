"""Всплывающие уведомления в правом верхнем углу окна.

``Notification`` — базовая карточка: заголовок, текст, крестик, автоскрытие
(пауза, пока курсор над карточкой), плавное появление. Наследники добавляют
свою картинку слева через ``build_leading()`` и задают ``kind``.

``NotificationCenter`` держит стопку карточек над содержимым окна: новые
сверху, не больше ``MAX_VISIBLE``, сдвигаются при закрытии соседей.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from PySide6.QtCore import (
    QEasingCurve,
    QElapsedTimer,
    QEvent,
    QObject,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QImage, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.models.track import Track
from quantis.ui import resources
from quantis.ui.corners import corner
from quantis.ui.image_fx import fill_crop
from quantis.ui.themes.spec import ThemeSpec, qcolor
from quantis.ui.views.widgets.glass import compositor_for, paint_glass

NotificationKind = Literal["info", "success", "error"]


class Notification(QFrame):
    """Базовое уведомление. Показывать через ``NotificationCenter.push``."""

    M = 14
    """Поле под тень вокруг карточки."""
    WIDTH = 340
    """Ширина карточки (без поля под тень)."""
    RADIUS = 18
    DEFAULT_TIMEOUT_MS = 4500

    closed = Signal()
    clicked = Signal()

    def __init__(
        self,
        title: str,
        message: str = "",
        *,
        kind: NotificationKind = "info",
        timeout_ms: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("notification")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._kind: NotificationKind = kind
        self._timeout_ms = self.DEFAULT_TIMEOUT_MS if timeout_ms is None else timeout_ms
        self._remaining_ms = self._timeout_ms
        self._elapsed = QElapsedTimer()
        self._closing = False

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)

        row = QHBoxLayout(self)
        row.setContentsMargins(self.M + 14, self.M + 12, self.M + 8, self.M + 12)
        row.setSpacing(12)

        leading = self.build_leading()
        if leading is not None:
            row.addWidget(leading, 0, Qt.AlignmentFlag.AlignVCenter)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        self._title = QLabel(title)
        self._title.setObjectName("notificationTitle")
        self._title.setWordWrap(True)
        texts.addWidget(self._title)
        self._message = QLabel(message)
        self._message.setObjectName("notificationText")
        self._message.setWordWrap(True)
        self._message.setVisible(bool(message))
        texts.addWidget(self._message)
        row.addLayout(texts, stretch=1)

        self._close_btn = QToolButton()
        self._close_btn.setObjectName("notificationClose")
        self._close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close_btn.setIconSize(QSize(12, 12))
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setToolTip("Закрыть")
        self._close_btn.clicked.connect(self.dismiss)
        row.addWidget(self._close_btn, 0, Qt.AlignmentFlag.AlignTop)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(0.0)
        self.setGraphicsEffect(self._opacity)
        self._fade = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_done: Callable[[], None] | None = None
        self._fade.finished.connect(self._on_fade_finished)

        self.setFixedWidth(self.WIDTH + 2 * self.M)
        self.hide()

    # --- для наследников ---------------------------------------------------

    def build_leading(self) -> QWidget | None:
        """Виджет слева от текста (обложка, значок). По умолчанию — нет."""
        return None

    @property
    def kind(self) -> NotificationKind:
        return self._kind

    @property
    def message(self) -> str:
        return self._message.text()

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_message(self, text: str) -> None:
        self._message.setText(text)
        self._message.setVisible(bool(text))

    def theme(self) -> ThemeSpec:
        found = compositor_for(self)
        if found is not None:
            return found[0].theme
        from quantis.ui.preferences import UiPreferences

        return UiPreferences().theme

    # --- жизненный цикл ----------------------------------------------------

    def popup(self) -> None:
        """Показать с проявлением и запустить таймер автоскрытия."""
        color = qcolor(self.theme().colors.text_soft)
        self._close_btn.setIcon(resources.load_icon("close.svg", color))
        self.adjustSize()
        self.show()
        self.raise_()
        self._animate_opacity(1.0)
        self._start_timer()

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._animate_opacity(0.0, on_done=self._finish)

    def _finish(self) -> None:
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def _animate_opacity(
        self, target: float, on_done: Callable[[], None] | None = None
    ) -> None:
        self._fade.stop()
        self._fade_done = on_done
        self._fade.setStartValue(self._opacity.opacity())
        self._fade.setEndValue(target)
        self._fade.start()

    def _on_fade_finished(self) -> None:
        done, self._fade_done = self._fade_done, None
        if done is not None:
            done()

    def _start_timer(self) -> None:
        if self._timeout_ms <= 0 or self._closing:
            return  # 0 — висит, пока не закроют
        self._elapsed.start()
        self._timer.start(max(500, self._remaining_ms))

    def enterEvent(self, event) -> None:
        if self._timer.isActive():
            self._remaining_ms -= self._elapsed.elapsed()
            self._timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._start_timer()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.card_rect().contains(
            event.position()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    # --- отрисовка ---------------------------------------------------------

    def card_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)

    def accent_color(self) -> QColor:
        colors = self.theme().colors
        rgb = {
            "success": colors.ok_rgb,
            "error": colors.bad_rgb,
        }.get(self._kind, colors.hl_rgb)
        return qcolor(rgb)

    def paintEvent(self, event) -> None:
        theme = self.theme()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self.card_rect()
        radius = corner(self.RADIUS)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(7):  # мягкая тень без QGraphicsDropShadowEffect
            painter.setBrush(QColor(0, 0, 0, 12))
            painter.drawRoundedRect(
                card.adjusted(-i * 1.6, -i + 4, i * 1.6, i * 1.6 + 6),
                radius + i,
                radius + i,
            )
        path = QPainterPath()
        path.addRoundedRect(card, radius, radius)
        tint = qcolor(theme.colors.popup_bg)
        tint.setAlpha(max(tint.alpha(), 200))
        if not paint_glass(self, painter, path, tint):
            painter.fillPath(path, qcolor(theme.colors.list_bg))

        # Полоска цвета вида уведомления у левого края.
        accent = self.accent_color()
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(QRectF(card.left(), card.top(), 3, card.height()), accent)
        painter.restore()

        ink = qcolor(theme.colors.ink_rgb)
        ink.setAlpha(36)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(ink, 1))
        painter.drawPath(path)
        painter.end()


class CoverThumb(QWidget):
    """Квадратная обложка со скруглением; без файла — заглушка цвета темы."""

    def __init__(self, path: str | None, size: int = 44, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._image = QImage()
        if path and Path(path).is_file():
            image = QImage(path)
            if not image.isNull():
                ratio = self.devicePixelRatioF() or 1.0
                self._image = fill_crop(image, QSize(size, size) * ratio)
                self._image.setDevicePixelRatio(ratio)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        radius = corner(10)
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
        if self._image.isNull():
            color = QColor(255, 255, 255, 30)
            painter.fillPath(path, color)
        else:
            painter.setClipPath(path)
            painter.drawImage(self.rect(), self._image)
        painter.end()


class DownloadNotification(Notification):
    """«Трек скачан» / «Не удалось скачать» с обложкой трека."""

    def __init__(
        self,
        track: Track,
        ok: bool,
        cover_path: str | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._cover_path = cover_path
        artist = (track.author or "").strip()
        name = (track.title or "").strip() or "Без названия"
        super().__init__(
            "Трек скачан" if ok else "Не удалось скачать",
            f"{artist} — {name}" if artist else name,
            kind="success" if ok else "error",
            timeout_ms=None if ok else 7000,
            parent=parent,
        )
        self.track = track

    def build_leading(self) -> QWidget | None:
        return CoverThumb(self._cover_path)


class NotificationCenter(QObject):
    """Стопка уведомлений в правом верхнем углу ``host``.

    ``top_offset`` — откуда начинать по вертикали (под шапкой окна).
    """

    MAX_VISIBLE = 4
    GAP = -16
    """Между карточками: поля под тень перекрываются, видимый зазор ~12px."""
    RIGHT = 2

    def __init__(
        self,
        host: QWidget,
        top_offset: Callable[[], int] | None = None,
    ) -> None:
        super().__init__(host)
        self._host = host
        self._top_offset = top_offset or (lambda: 0)
        self._items: list[Notification] = []
        host.installEventFilter(self)

    @property
    def notifications(self) -> list[Notification]:
        return list(self._items)

    def push(self, notification: Notification) -> Notification:
        notification.setParent(self._host)
        notification.closed.connect(lambda n=notification: self._remove(n))
        self._items.insert(0, notification)
        while len(self._items) > self.MAX_VISIBLE:
            self._items[-1].dismiss()
            self._items.pop()
        notification.popup()
        self._layout()
        return notification

    def clear(self) -> None:
        for item in list(self._items):
            item.dismiss()

    def _remove(self, notification: Notification) -> None:
        if notification in self._items:
            self._items.remove(notification)
        self._layout()

    def _layout(self) -> None:
        y = self._top_offset()
        for item in self._items:
            item.adjustSize()
            x = self._host.width() - item.width() - self.RIGHT
            item.move(QPoint(max(0, x), y))
            item.raise_()
            y += item.height() + self.GAP

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._host and event.type() == QEvent.Type.Resize:
            self._layout()
        return False
