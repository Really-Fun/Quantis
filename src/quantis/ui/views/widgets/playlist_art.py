"""Арт во весь фон страницы плейлиста.

Слой монтируется между фоном окна и интерфейсом (``BodyWithWallpaper``): справа
арт виден целиком, слева он уходит в затемнение, на котором лежит список.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QRect, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QImage, QImageReader, QLinearGradient, QPainter
from PySide6.QtWidgets import QWidget

from quantis.ui.image_fx import blur_image, fill_crop
from quantis.ui.preferences import UiPreferences
from quantis.ui.themes.spec import qcolor
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor
from quantis.ui.views.widgets.cover_art import (
    _crop_letterbox,
    gradient_for_name,
    track_cover_file,
)

_ART_MAX_SIDE = 1600
_SHARP_WIDTH = 1000
"""Обложка от этой ширины считается крупной: её не размывает растяжение."""
_TRACKS_TO_PROBE = 12
_FADE_MS = 260
_TOP_FADE = 110
"""Высота (px), на которой верх арта растворяется в фоне окна."""


def pick_art_path(playlist) -> str | None:
    """Своя картинка плейлиста, иначе обложка одного из первых треков:
    первая крупная, а если крупных нет — первая, что есть на диске."""
    own = getattr(playlist, "cover_path", None)
    if own and Path(own).suffix.lower() != ".svg" and Path(own).is_file():
        return str(own)
    tracks = getattr(getattr(playlist, "tracks", None), "values", None) or []
    fallback: str | None = None
    for track in tracks[:_TRACKS_TO_PROBE]:
        path = track_cover_file(track)
        if not path.is_file():
            continue
        size = QImageReader(str(path)).size()
        if not size.isValid():
            continue
        if size.width() >= _SHARP_WIDTH:
            return str(path)
        if fallback is None:
            fallback = str(path)
    return fallback


def _column_step(image: QImage, x: int, rows: range) -> float:
    """Средний перепад цвета между столбцами ``x - 2`` и ``x + 2``."""
    total = 0
    for y in rows:
        a, b = image.pixelColor(x - 2, y), image.pixelColor(x + 2, y)
        total += (
            abs(a.red() - b.red())
            + abs(a.green() - b.green())
            + abs(a.blue() - b.blue())
        )
    return total / (3 * max(1, len(rows)))


def crop_side_bars(image: QImage) -> QImage:
    """Обложки треков YouTube Music — квадрат по центру кадра 16:9 с полями по
    бокам. Поля срезаем: на арте во весь фон их край виден как линейка.

    Признак — резкий вертикальный шов ровно по границам центрального квадрата,
    которого нет чуть в стороне от них."""
    w, h = image.width(), image.height()
    if h < 64 or not 1.7 <= w / h <= 1.85:
        return image
    left = (w - h) // 2
    right = left + h
    rows = range(h // 10, h - h // 10, max(1, h // 24))
    for seam, inside in ((left, left + 12), (right, right - 12)):
        step = _column_step(image, seam, rows)
        if step < 10 or step < 3 * _column_step(image, inside, rows):
            return image
    return image.copy(left, 0, h, h)


def load_art(path: str | None) -> QImage:
    if not path:
        return QImage()
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > _ART_MAX_SIDE:
        reader.setScaledSize(
            size.scaled(
                _ART_MAX_SIDE, _ART_MAX_SIDE, Qt.AspectRatioMode.KeepAspectRatio
            )
        )
    image = reader.read()
    if image.isNull():
        return image
    image = _crop_letterbox(image).convertToFormat(QImage.Format.Format_RGB32)
    return crop_side_bars(image)


def placeholder_art(name: str) -> QImage:
    """Подборка без обложек: мягкий градиент цветов её названия."""
    first, second = gradient_for_name(name or "?")
    image = QImage(160, 90, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 160, 90)
    gradient.setColorAt(0.0, first.darker(260))
    gradient.setColorAt(1.0, second.darker(140))
    painter.fillRect(image.rect(), gradient)
    painter.end()
    return image


def _alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlphaF(alpha)
    return out


def _fade_left_edge(image: QImage, width: int) -> QImage:
    out = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(out)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    gradient = QLinearGradient(0, 0, width, 0)
    gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
    gradient.setColorAt(1.0, QColor(0, 0, 0, 255))
    painter.fillRect(0, 0, width, out.height(), gradient)
    painter.end()
    return out


def fade_top_edge(image: QImage, height: int) -> QImage:
    """Верх кадра плавно уходит в прозрачность: под шапкой окна арт не
    обрывается по линейке, а вырастает из общего фона."""
    out = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    if height <= 0:
        return out
    painter = QPainter(out)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    gradient = QLinearGradient(0, 0, 0, height)
    gradient.setColorAt(0.0, QColor(0, 0, 0, 0))
    gradient.setColorAt(1.0, QColor(0, 0, 0, 255))
    painter.fillRect(0, 0, out.width(), height, gradient)
    painter.end()
    return out


def compose_art(
    art: QImage, size: QSize, scrim: QColor, *, sharp: bool = True
) -> QImage:
    """Кадр фона: размытый арт на всю площадь, поверх него сам арт по правому
    краю во всю высоту и затемнение цветом темы слева и снизу."""
    w, h = size.width(), size.height()
    if w <= 0 or h <= 0:
        return QImage()
    out = QImage(w, h, QImage.Format.Format_RGB32)
    out.fill(scrim)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    if not art.isNull():
        soft = fill_crop(art, QSize(max(2, w // 4), max(2, h // 4)))
        painter.drawImage(QRect(0, 0, w, h), blur_image(soft, 0.85))
        if sharp:
            art_w = round(art.width() * h / art.height())
            if art_w >= w:
                painter.drawImage(0, 0, fill_crop(art, size))
            else:
                front = art.scaled(
                    art_w,
                    h,
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                front = _fade_left_edge(front, max(1, int(art_w * 0.4)))
                painter.drawImage(w - art_w, 0, front)

    side = QLinearGradient(0, 0, w, 0)
    side.setColorAt(0.0, _alpha(scrim, 0.90))
    side.setColorAt(0.38, _alpha(scrim, 0.74))
    side.setColorAt(0.68, _alpha(scrim, 0.22))
    side.setColorAt(1.0, _alpha(scrim, 0.06))
    painter.fillRect(out.rect(), side)

    edges = QLinearGradient(0, 0, 0, h)
    edges.setColorAt(0.0, _alpha(scrim, 0.30))
    edges.setColorAt(0.18, _alpha(scrim, 0.0))
    edges.setColorAt(0.72, _alpha(scrim, 0.0))
    edges.setColorAt(1.0, _alpha(scrim, 0.55))
    painter.fillRect(out.rect(), edges)
    painter.end()
    return out


class PlaylistArtLayer(QWidget):
    """Фоновый слой страницы плейлиста: обложка из режима фона «Обложка»,
    показанная артом. Появляется и уходит плавно.

    Свою картинку, клип и «Цвета трека» слой не заслоняет: он виден только
    там, где фон и так показывает обложку (режим «Обложка» и клип, которого
    ещё нет). Арт — обложка играющего трека; пока ничего не играло — обложка
    самой подборки.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("playlistArtLayer")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self._prefs = UiPreferences()
        self._prefs.theme_changed.connect(self._invalidate)
        self._compositor: BackdropCompositor | None = None
        # арт самой подборки — запасной, пока у фона нет обложки трека
        self._own = QImage()
        self._own_sharp = False
        self._own_key: tuple[object, ...] | None = None
        # что рисуем сейчас
        self._art = QImage()
        self._sharp = False
        self._source: object = None
        self._wanted = False
        self._frame = QImage()
        self._opacity = 0.0
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(_FADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._on_fade)
        self._fade.finished.connect(self._on_fade_done)
        self.hide()

    def bind_backdrop(self, compositor: BackdropCompositor) -> None:
        """Фон окна: его режим решает, виден ли арт, и даёт обложку трека."""
        self._compositor = compositor
        compositor.frame_changed.connect(self._sync)
        self._sync()

    def set_art(self, path: str | None, name: str = "") -> None:
        """Арт подборки из файла; без файла — градиент по её названию."""
        size = os.path.getsize(path) if path and os.path.isfile(path) else 0
        key = (path, size) if size else (None, name)
        if key == self._own_key:
            return
        self._own_key = key
        image = load_art(path) if size else QImage()
        self._own_sharp = not image.isNull()
        self._own = image if self._own_sharp else placeholder_art(name)
        self._sync()

    def set_shown(self, shown: bool) -> None:
        """Страница плейлиста открыта или закрыта."""
        self._wanted = shown
        self._sync()

    def _backdrop_shows_cover(self) -> bool:
        comp = self._compositor
        if comp is None:
            return True
        return comp.mode == "cover" or (
            comp.mode == "video" and not comp.has_video_frame()
        )

    def _sync(self) -> None:
        """Сверяет арт и видимость с фоном. Зовётся на каждый кадр фона,
        поэтому без изменений ничего не делает."""
        visible = self._wanted and self._backdrop_shows_cover()
        cover = QImage() if self._compositor is None else self._compositor.cover_image()
        source = self._own_key if cover.isNull() else cover.cacheKey()
        if visible and source != self._source:
            self._source = source
            if cover.isNull():
                self._art, self._sharp = self._own, self._own_sharp
            else:
                # у фона обложка уменьшена до 96 px — арту нужен сам файл
                full = load_art(self._compositor.cover_path())
                self._art = _crop_letterbox(cover) if full.isNull() else full
                self._sharp = True
            self._invalidate()
        if self._compositor is not None:
            self._compositor.set_cover_hidden(visible)  # под артом дрейф не виден
        self._fade_to(1.0 if visible else 0.0)

    def _fade_to(self, target: float) -> None:
        if self._fade.endValue() == target and (
            self._fade.state() == QVariantAnimation.State.Running
            or self._opacity == target
        ):
            return
        self._fade.stop()
        if target > 0.0:
            self.show()
        self._fade.setStartValue(self._opacity)
        self._fade.setEndValue(target)
        self._fade.start()

    def _on_fade(self, value) -> None:
        self._opacity = float(value)
        self.update()

    def _on_fade_done(self) -> None:
        if self._opacity <= 0.0:
            self.hide()

    def _invalidate(self) -> None:
        self._frame = QImage()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._frame = QImage()

    def _ensure_frame(self) -> QImage:
        dpr = self.devicePixelRatioF()
        size = self.size() * dpr
        if self._frame.isNull() or self._frame.size() != size:
            scrim = qcolor(self._prefs.theme.colors.bg)
            frame = compose_art(self._art, size, scrim, sharp=self._sharp)
            self._frame = fade_top_edge(frame, round(_TOP_FADE * dpr))
            self._frame.setDevicePixelRatio(dpr)
        return self._frame

    def paintEvent(self, event) -> None:
        if self._opacity <= 0.0:
            return
        frame = self._ensure_frame()
        if frame.isNull():
            return
        painter = QPainter(self)
        painter.setOpacity(self._opacity)
        painter.drawImage(0, 0, frame)
        painter.end()
