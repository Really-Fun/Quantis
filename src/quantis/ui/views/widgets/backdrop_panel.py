"""Панель «Фон»: поповер под кнопкой в шапке.

Четыре плитки с живыми превью (цвета трека / обложка / своя картинка / клип),
ползунки «Размытие» и «Затемнение», «Движение» — только для обложки. Всё
состояние — в ``UiPreferences`` (``backdrop_mode`` и прочие), поэтому раздел
«Обои» в настройках показывает то же самое.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from quantis.ui.image_fx import fill_crop
from quantis.ui.preferences import BackdropMode, UiPreferences
from quantis.ui.themes.spec import ThemeSpec, qcolor
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor
from quantis.ui.views.widgets.glass import paint_glass

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
VIDEO_EXT = (".mp4", ".webm", ".mkv", ".mov", ".m4v")

HINTS: dict[str, str] = {
    "palette": "Мягкий градиент из цветов обложки. Меняется вместе с треком.",
    "cover": "Обложка во весь экран, размытая. «Движение» — медленный дрейф.",
    "image": "Любая картинка. Можно просто перетащить файл в окно.",
    "video": "Клип трека с YouTube, без звука, в такт музыке. Или свой видеофайл.",
}


def backdrop_kind(path: str) -> str | None:
    """ "image" / "video" по расширению файла, иначе None."""
    suffix = Path(path).suffix.lower()
    if suffix in IMAGE_EXT:
        return "image"
    if suffix in VIDEO_EXT:
        return "video"
    return None


def apply_backdrop_file(prefs: UiPreferences, path: str) -> bool:
    """Картинка или видео фоном (выбор файла, перетаскивание в окно)."""
    kind = backdrop_kind(path)
    if kind == "image":
        prefs.set_wallpaper_path(path)
        prefs.set_backdrop_mode("image")
        return True
    if kind == "video":
        prefs.set_backdrop_video_file(path)
        return True
    return False


class BackdropTiles(QWidget):
    """Четыре плитки выбора фона с живыми превью."""

    TW, TH, GAP, LH = 168, 94, 12, 26
    ITEMS: tuple[tuple[BackdropMode, str], ...] = (
        ("palette", "Цвета трека"),
        ("cover", "Обложка"),
        ("image", "Своя картинка"),
        ("video", "Клип"),
    )
    picked = Signal(str)

    def __init__(
        self,
        compositor: BackdropCompositor,
        prefs: UiPreferences,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._compositor = compositor
        self._prefs = prefs
        self._fits: dict[str, tuple[int, QImage]] = {}
        self.setFixedSize(self.TW * 2 + self.GAP, (self.TH + self.LH) * 2 + self.GAP)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _rect(self, index: int) -> QRectF:
        col, row = index % 2, index // 2
        return QRectF(
            col * (self.TW + self.GAP),
            row * (self.TH + self.LH + self.GAP),
            self.TW,
            self.TH,
        )

    def mode_at(self, pos: QPointF) -> BackdropMode | None:
        for index, (mode, _) in enumerate(self.ITEMS):
            if self._rect(index).adjusted(0, 0, 0, self.LH).contains(pos):
                return mode
        return None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        mode = self.mode_at(event.position())
        if mode is not None:
            self.picked.emit(mode)

    def _fit(self, slot: str, image: QImage, size: QSize) -> QImage:
        """Превью под плитку; пересчёт, только когда сменилась картинка."""
        cached = self._fits.get(slot)
        if cached is not None and cached[0] == image.cacheKey():
            return cached[1]
        fit = fill_crop(image, size)
        self._fits[slot] = (image.cacheKey(), fit)
        return fit

    def _preview(self, painter: QPainter, mode: str, rect: QRectF) -> None:
        theme = self._compositor.theme
        comp = self._compositor
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(rect, qcolor(theme.colors.bg))
        pixel = QSize(int(rect.width() * 2), int(rect.height() * 2))
        if mode == "palette":
            palette = comp.palette
            for cx, cy, color, alpha in (
                (0.25, 0.3, palette.accent, 200),
                (0.85, 0.1, palette.accent2, 170),
                (0.6, 1.0, palette.deep, 255),
            ):
                _radial(painter, rect, cx, cy, color, alpha)
        elif mode == "cover":
            soft = comp.cover_preview()
            if not soft.isNull():
                painter.drawImage(rect.adjusted(-20, -20, 20, 20), soft)
            raw = comp.cover_image()
            if not raw.isNull():
                box = QRectF(rect.center().x() - 23, rect.center().y() - 23, 46, 46)
                clip = QPainterPath()
                clip.addRoundedRect(box, 9, 9)
                painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
                painter.drawImage(box, raw)
        else:
            source = comp.wallpaper_image() if mode == "image" else comp.video_image()
            if not source.isNull():
                painter.drawImage(rect, self._fit(mode, source, pixel))
                painter.fillRect(rect, QColor(0, 0, 0, 40))
            else:
                painter.fillRect(rect, _ink(theme, 10))
                painter.setPen(qcolor(theme.colors.text_dim))
                painter.setFont(_font(11.5, QFont.Weight.Medium))
                text = "Выбрать файл" if mode == "image" else "С YouTube или файл"
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
            if mode == "video":
                badge = QRectF(rect.right() - 34, rect.y() + 8, 26, 18)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 130))
                painter.drawRoundedRect(badge, 6, 6)
                painter.setBrush(QColor(255, 255, 255))
                c = badge.center()
                painter.drawPolygon(
                    [c + QPointF(-3, -5), c + QPointF(-3, 5), c + QPointF(5, 0)]
                )
        painter.restore()

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = self._compositor.theme
        current = self._prefs.backdrop_mode
        text = qcolor(theme.colors.text)
        dim = qcolor(theme.colors.text_soft)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        for index, (mode, name) in enumerate(self.ITEMS):
            rect = self._rect(index)
            self._preview(painter, mode, rect)
            on = current == mode
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if on:
                painter.setPen(QPen(text, 2))
                painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 13, 13)
                center = QPointF(rect.x() + 16, rect.y() + 16)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(text)
                painter.drawEllipse(center, 8, 8)
                pen = QPen(qcolor(theme.colors.bg), 1.8)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawPolyline(
                    [
                        center + QPointF(-3.5, 0),
                        center + QPointF(-1, 2.8),
                        center + QPointF(3.8, -2.6),
                    ]
                )
            else:
                painter.setPen(QPen(_ink(theme, 30), 1))
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)
            weight = QFont.Weight.DemiBold if on else QFont.Weight.Medium
            painter.setFont(_font(13, weight))
            painter.setPen(text if on else dim)
            painter.drawText(
                QRectF(rect.x() + 2, rect.bottom() + 4, rect.width(), 20),
                Qt.AlignmentFlag.AlignLeft,
                name,
            )
        painter.end()


class BackdropPanel(QFrame):
    """Поповер «Фон». Живёт в каркасе окна (``BackgroundFrame``), поэтому
    рисуется матовым стеклом, как остальные панели."""

    M = 22
    """Поле под тень."""
    closed = Signal()

    def __init__(
        self,
        compositor: BackdropCompositor,
        prefs: UiPreferences | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("backdropPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._compositor = compositor
        self._prefs = prefs or UiPreferences()
        self._anchor: QWidget | None = None

        box = QVBoxLayout(self)
        box.setContentsMargins(self.M + 22, self.M + 18, self.M + 22, self.M + 20)
        box.setSpacing(0)
        head = QHBoxLayout()
        title = QLabel("Фон")
        title.setObjectName("backdropPanelTitle")
        head.addWidget(title)
        head.addStretch(1)
        self._pick = QToolButton()
        self._pick.setObjectName("backdropPanelPick")
        self._pick.setText("Выбрать файл…")
        self._pick.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pick.clicked.connect(lambda: self.choose_file(self._prefs.backdrop_mode))
        head.addWidget(self._pick)
        box.addLayout(head)
        box.addSpacing(14)

        self._tiles = BackdropTiles(compositor, self._prefs)
        self._tiles.picked.connect(self.on_pick)
        box.addWidget(self._tiles)
        box.addSpacing(6)
        self._hint = QLabel()
        self._hint.setObjectName("backdropPanelHint")
        self._hint.setWordWrap(True)
        self._hint.setFixedHeight(36)
        box.addWidget(self._hint)
        box.addSpacing(8)
        self._blur = self._slider_row(box, "Размытие", self._prefs.set_backdrop_blur)
        self._dim = self._slider_row(box, "Затемнение", self._prefs.set_backdrop_dim)
        self._motion_row = QWidget()
        row = QHBoxLayout(self._motion_row)
        row.setContentsMargins(0, 6, 0, 0)
        label = QLabel("Движение")
        label.setObjectName("backdropPanelLabel")
        row.addWidget(label)
        row.addStretch(1)
        self._motion = _Switch(compositor)
        self._motion.setObjectName("backdropMotion")
        self._motion.toggled.connect(self._prefs.set_backdrop_motion)
        row.addWidget(self._motion)
        box.addWidget(self._motion_row)

        self._prefs.wallpaper_changed.connect(self.refresh)
        compositor.frame_changed.connect(self._on_frame)
        self.refresh()
        self.hide()

    def _slider_row(
        self, box: QVBoxLayout, name: str, apply: Callable[[float], None]
    ) -> QSlider:
        row = QHBoxLayout()
        row.setSpacing(12)
        label = QLabel(name)
        label.setObjectName("backdropPanelLabel")
        label.setFixedWidth(104)
        row.addWidget(label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setObjectName("backdropSlider")
        slider.setRange(0, 100)
        slider.valueChanged.connect(lambda v: apply(v / 100))
        row.addWidget(slider, 1)
        box.addLayout(row)
        box.addSpacing(10)
        return slider

    # --- состояние -------------------------------------------------------

    def refresh(self) -> None:
        mode = self._prefs.backdrop_mode
        self._hint.setText(HINTS[mode])
        self._pick.setVisible(mode in ("image", "video"))
        for slider, value in (
            (self._blur, self._prefs.backdrop_blur),
            (self._dim, self._prefs.backdrop_dim),
        ):
            if slider.isSliderDown():
                continue  # не дёргаем ползунок под пальцем
            slider.blockSignals(True)
            slider.setValue(round(value * 100))
            slider.blockSignals(False)
        self._motion.blockSignals(True)
        self._motion.setChecked(self._prefs.backdrop_motion)
        self._motion.blockSignals(False)
        self._motion_row.setVisible(mode == "cover")  # дрейф есть только у обложки
        self.adjustSize()
        self._place()
        self._tiles.update()

    def _on_frame(self) -> None:
        if self.isVisible():
            self._tiles.update()  # живые превью: клип, цвета трека

    def on_pick(self, mode: str) -> None:
        prefs = self._prefs
        if mode in ("palette", "cover"):
            prefs.set_backdrop_mode(mode)  # type: ignore[arg-type]
        elif mode == "image":
            if prefs.backdrop_mode == "image" or not self._compositor.has_wallpaper():
                self.choose_file("image")
            else:
                prefs.set_backdrop_mode("image")
        elif mode == "video":
            if prefs.backdrop_mode == "video":
                self.choose_file("video")
            else:
                prefs.set_backdrop_mode("video")  # клипы треков с YouTube

    def choose_file(self, mode: str) -> None:
        if mode == "image":
            title, pattern = (
                "Картинка для фона",
                "Картинки (*.jpg *.jpeg *.png *.webp *.bmp *.gif)",
            )
        else:
            title, pattern = "Видео для фона", "Видео (*.mp4 *.webm *.mkv *.mov *.m4v)"
        path, _ = QFileDialog.getOpenFileName(self, title, str(Path.home()), pattern)
        if path:
            apply_backdrop_file(self._prefs, path)

    # --- показ -----------------------------------------------------------

    def toggle(self, anchor: QWidget) -> None:
        if self.isVisible():
            self.close_panel()
            return
        self._anchor = anchor
        self.refresh()
        self.show()
        self.raise_()
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def close_panel(self) -> None:
        if not self.isVisible():
            return
        self.hide()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        self.closed.emit()

    def _place(self) -> None:
        host, anchor = self.parentWidget(), self._anchor
        if host is None or anchor is None:
            return
        corner = anchor.mapTo(host, anchor.rect().bottomRight())
        x = min(corner.x() + self.M, host.width() - self.width())
        self.move(max(0, x - self.width() + 2 * self.M), corner.y() - self.M + 4)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.KeyPress and getattr(event, "key", lambda: 0)() == (
            Qt.Key.Key_Escape
        ):
            self.close_panel()
            return True
        if kind == QEvent.Type.MouseButtonPress and isinstance(event, QMouseEvent):
            point = self.mapFromGlobal(event.globalPosition().toPoint())
            inside = self._card().contains(QPointF(point))
            on_anchor = self._anchor is not None and self._anchor.rect().contains(
                self._anchor.mapFromGlobal(event.globalPosition().toPoint())
            )
            if not inside and not on_anchor:
                self.close_panel()
        return False

    def _card(self) -> QRectF:
        return QRectF(self.rect()).adjusted(self.M, self.M, -self.M, -self.M)

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = self._compositor.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = self._card()
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(10):  # мягкая тень без QGraphicsDropShadowEffect
            painter.setBrush(QColor(0, 0, 0, 10))
            painter.drawRoundedRect(
                card.adjusted(-i * 2, -i * 1.2 + 6, i * 2, i * 2 + 10), 24 + i, 24 + i
            )
        path = QPainterPath()
        path.addRoundedRect(card, 24, 24)
        tint = qcolor(theme.colors.popup_bg)
        tint.setAlpha(max(tint.alpha(), 190))
        if not paint_glass(self, painter, path, tint):
            painter.fillPath(path, qcolor(theme.colors.list_bg))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(_ink(theme, 36), 1))
        painter.drawPath(path)
        painter.end()


class _Switch(QAbstractButton):
    """Переключатель цветами темы: дорожка ``tint`` и ручка ``handle``."""

    def __init__(self, compositor: BackdropCompositor) -> None:
        super().__init__()
        self._compositor = compositor
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 24)

    def paintEvent(self, event: QPaintEvent) -> None:
        theme = self._compositor.theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(
            qcolor(theme.colors.tint) if self.isChecked() else _ink(theme, 46)
        )
        painter.drawRoundedRect(track, track.height() / 2, track.height() / 2)
        knob = track.height() - 6
        x = track.right() - knob - 3 if self.isChecked() else track.left() + 3
        painter.setBrush(qcolor(theme.colors.handle))
        painter.drawEllipse(QRectF(x, track.top() + 3, knob, knob))
        painter.end()


def _radial(
    painter: QPainter,
    rect: QRectF,
    cx: float,
    cy: float,
    color: QColor,
    alpha: int,
) -> None:
    gradient = QRadialGradient(
        QPointF(rect.x() + rect.width() * cx, rect.y() + rect.height() * cy),
        rect.width() * 0.7,
    )
    start, end = QColor(color), QColor(color)
    start.setAlpha(alpha)
    end.setAlpha(0)
    gradient.setColorAt(0, start)
    gradient.setColorAt(1, end)
    painter.fillRect(rect, gradient)


def _ink(theme: ThemeSpec, alpha: int) -> QColor:
    color = qcolor(theme.colors.ink_rgb)
    color.setAlpha(alpha)
    return color


def _font(px: float, weight: QFont.Weight) -> QFont:
    font = QFont(QApplication.font())
    font.setPixelSize(round(px))
    font.setWeight(weight)
    return font
