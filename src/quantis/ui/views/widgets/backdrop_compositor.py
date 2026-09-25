"""Фон окна одной картинкой: слой темы, обои, кадр видео.

Весь фон под интерфейсом собирается здесь и кэшируется; ``BackgroundFrame``
только блитит готовый кадр. Пересборка — лишь когда что-то поменялось
(кадр видео, фаза свечения, палитра, размер).

Слой темы (цвет, глубина, свечение, виньетка) мягкий, поэтому собирается в
половинном разрешении и растягивается.

Отсюда же — матовое стекло: ``glass()`` отдаёт размытую копию кадра для панелей
(см. ``ui/views/widgets/glass.py``). Пересчёт — только когда поменялся кадр, и не
чаще FPS видео-обоев (или 10 раз в секунду без видео); в эко-режиме — никогда.
"""

from __future__ import annotations

import math
from time import monotonic

from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QRadialGradient,
)

from quantis.ui.cover_accent import CoverPalette, fallback_palette
from quantis.ui.image_fx import blur_image, fill_crop, mean_luma
from quantis.ui.themes import registry
from quantis.ui.themes.spec import GlowSpec, ThemeSpec, qcolor

LUMA_SMOOTHING = 0.2
"""Доля нового кадра в сглаженной яркости клипа: автозатемнение без мигания."""
GLASS_MIN_INTERVAL = 0.1
"""Без видео стекло пересчитывается не чаще 10 раз в секунду: свечение и
переход палитры медленные, под размытием разница не видна."""
_FAST = Qt.TransformationMode.FastTransformation
_SMOOTH = Qt.TransformationMode.SmoothTransformation


class BackdropCompositor(QObject):
    frame_changed = Signal()
    """Кадр фона устарел — хозяину пора перерисоваться."""

    def __init__(self, theme: ThemeSpec | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self._theme = theme or registry.default()
        self._palette = fallback_palette(self._theme)
        self._size = QSize()
        self._dpr = 1.0
        self._phase = 0.0
        self._cinematic = False
        self._content = QRect()
        # статичные обои
        self._wallpaper = QImage()
        self._wallpaper_fit = QImage()
        self._dynamic = False
        # видео-фон
        self._video_active = False
        self._video = QImage()
        self._video_fit = QImage()
        # читаемость картинки/клипа
        self._dim = 0.3
        self._blur = 0.1
        self._luma: float | None = None
        self._media = QImage()
        self._media_key: tuple[object, ...] = ()
        # кэши
        self._soft = QImage()
        self._soft_dirty = True
        self._frame = QImage()
        self._frame_dirty = True
        # стекло
        self._glass = QImage()
        self._glass_key = 0
        self._glass_at = 0.0
        self._video_interval = 1 / 24
        self._eco = False
        self._glass_timer = QTimer(self)
        self._glass_timer.setSingleShot(True)
        self._glass_timer.timeout.connect(self.frame_changed.emit)

    # --- состояние -------------------------------------------------------

    @property
    def theme(self) -> ThemeSpec:
        return self._theme

    @property
    def palette(self) -> CoverPalette:
        return self._palette

    @property
    def cinematic(self) -> bool:
        return self._cinematic

    @property
    def look(self) -> tuple[float, float]:
        """(затемнение, размытие) картинки/клипа."""
        return self._dim, self._blur

    def set_look(self, dim: float, blur: float) -> None:
        if (dim, blur) != (self._dim, self._blur):
            self._dim, self._blur = dim, blur
            self._invalidate()

    def set_size(self, size: QSize, dpr: float = 1.0) -> None:
        if size == self._size and dpr == self._dpr:
            return
        self._size = QSize(size)
        self._dpr = dpr
        self._wallpaper_fit = QImage()
        self._video_fit = QImage()
        self._invalidate(soft=True)

    def set_theme(self, theme: ThemeSpec) -> None:
        if theme is self._theme:
            return
        self._theme = theme
        self._wallpaper_fit = QImage()
        self._glass = QImage()
        self._invalidate(soft=True)

    def set_eco(self, enabled: bool) -> None:
        """Окно в фоне: стекло не пересчитываем (последнее остаётся)."""
        self._eco = enabled

    def set_video_fps(self, fps: float) -> None:
        self._video_interval = 1 / max(1.0, fps)

    def set_palette(self, palette: CoverPalette) -> None:
        if palette == self._palette:
            return
        self._palette = palette
        glow = self._theme.backdrop.glow
        if glow is not None and glow.style == "cover":
            self._invalidate(soft=True)

    def set_phase(self, phase: float) -> None:
        if phase != self._phase:
            self._phase = phase
            self._invalidate(soft=True)

    def set_cinematic(self, enabled: bool) -> None:
        if enabled != self._cinematic:
            self._cinematic = enabled
            self._video_fit = QImage()
            self._invalidate()

    def set_content_rect(self, rect: QRect) -> None:
        """Зона контента в координатах окна: там идёт видео в театральном режиме."""
        if rect != self._content:
            self._content = QRect(rect)
            if self._cinematic:
                self._video_fit = QImage()
                self._invalidate()

    def set_wallpaper(self, image: QImage | None) -> None:
        self._wallpaper = QImage() if image is None else image
        self._wallpaper_fit = QImage()
        self._invalidate()

    def set_dynamic(self, enabled: bool) -> None:
        """Видео-обои включены: статичная картинка не показывается."""
        if enabled != self._dynamic:
            self._dynamic = enabled
            self._invalidate()

    def set_video_active(self, active: bool) -> None:
        if active != self._video_active:
            self._video_active = active
            self._luma = None  # новый клип — яркость считаем заново
            self._invalidate()

    def set_video_frame(self, image: QImage | None) -> None:
        self._video = QImage() if image is None else image
        self._video_fit = QImage()
        if self._video_active:
            self._invalidate()

    def has_video_frame(self) -> bool:
        return self._video_active and not self._video.isNull()

    def _invalidate(self, *, soft: bool = False) -> None:
        if soft:
            self._soft_dirty = True
        self._frame_dirty = True
        self.frame_changed.emit()

    # --- кадр ------------------------------------------------------------

    def frame(self) -> QImage:
        """Фон всего окна в пикселях устройства (кэш)."""
        if self._frame_dirty or self._frame.isNull():
            self._frame = self._compose()
            self._frame_dirty = False
        return self._frame

    def _device_size(self, scale: float = 1.0) -> QSize:
        return QSize(
            max(1, round(self._size.width() * self._dpr * scale)),
            max(1, round(self._size.height() * self._dpr * scale)),
        )

    def _compose(self) -> QImage:
        size = self._device_size()
        image = QImage(size, QImage.Format.Format_RGB32)
        image.setDevicePixelRatio(self._dpr)
        painter = QPainter(image)
        rect = QRect(QPoint(0, 0), self._size)
        if self._cinematic:
            painter.fillRect(rect, QColor(0, 0, 0))
            if self.has_video_frame() and not self._content.isEmpty():
                self._paint_video(painter, self._content)
                _paint_cinematic_dim(painter, self._content)
            painter.end()
            return image

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.has_video_frame():
            painter.drawImage(rect, self._media_layer(self._video, smooth_luma=True))
        else:
            painter.drawImage(rect, self._soft_layer())
            if not self._dynamic:
                self._paint_wallpaper(painter, rect)
        painter.end()
        return image

    # --- картинка/клип под интерфейсом -----------------------------------

    def _blur_amount(self, scale: float) -> float:
        """Ползунок «Размытие» → ``blur_image``: 0 — резко, 0.1 — ~1.8×, 1 — 25×
        (относительно полного разрешения; ``scale`` — масштаб холста)."""
        factor = (1 + 24 * math.pow(self._blur, 1.5)) * scale
        return max(0.0, (factor - 1) / 39)

    def _media_layer(self, source: QImage, *, smooth_luma: bool) -> QImage:
        """Картинка или кадр клипа во всю силу + затемнение для читаемости.

        Затемнение — цветом фона темы (в светлой теме это осветление): доля от
        ползунка плюс автоматическая добавка, если кадр слишком яркий для текста.
        У клипа яркость сглажена по кадрам, чтобы затемнение не мигало."""
        size = self._device_size(0.5)
        key = (
            source.cacheKey(),
            size.width(),
            size.height(),
            self._dim,
            self._blur,
            self._palette.accent.rgba(),
            self._theme.id,
        )
        if key == self._media_key and not self._media.isNull():
            return self._media
        image = blur_image(fill_crop(source, size), self._blur_amount(0.5))
        if image.format() != QImage.Format.Format_RGB32:
            image = image.convertToFormat(QImage.Format.Format_RGB32)
        luma = mean_luma(image)
        if self._theme.is_light:
            luma = 1 - luma  # на светлой теме мешает тёмный кадр
        if smooth_luma and self._luma is not None:
            luma = (1 - LUMA_SMOOTHING) * self._luma + LUMA_SMOOTHING * luma
        self._luma = luma

        base = qcolor(self._theme.colors.bg)
        base.setAlpha(255)
        w, h = image.width(), image.height()
        painter = QPainter(image)
        alpha = 0.1 + self._dim * 0.7
        need = 1 - 0.3 / max(0.3, luma * (1 - alpha))
        alpha = min(0.9, alpha + max(0.0, need) * (1 - alpha))
        painter.fillRect(0, 0, w, h, _with_alpha(base, 255 * alpha))
        accent = self._palette.accent
        tint = QRadialGradient(w * 0.2, h * 0.3, w * 0.6)
        tint.setColorAt(0, _with_alpha(accent, 40))
        tint.setColorAt(1, _with_alpha(accent, 0))
        painter.fillRect(0, 0, w, h, tint)
        side = QLinearGradient(0, 0, w * 0.55, 0)
        side.setColorAt(0, _with_alpha(base, 110))
        side.setColorAt(1, _with_alpha(base, 0))
        painter.fillRect(0, 0, w, h, side)
        veil = QLinearGradient(0, 0, 0, h)
        veil.setColorAt(0, _with_alpha(base, 70))
        veil.setColorAt(0.55, _with_alpha(base, 40))
        veil.setColorAt(1, _with_alpha(base, 150))
        painter.fillRect(0, 0, w, h, veil)
        painter.end()
        self._media, self._media_key = image, key
        return image

    def _paint_video(self, painter: QPainter, rect: QRect) -> None:
        target = QSize(
            round(rect.width() * self._dpr), round(rect.height() * self._dpr)
        )
        if self._video_fit.isNull() or self._video_fit.size() != target:
            self._video_fit = self._video.scaled(
                target, Qt.AspectRatioMode.KeepAspectRatioByExpanding, _FAST
            )
            self._video_fit.setDevicePixelRatio(self._dpr)
        fit = self._video_fit
        x = rect.x() + (rect.width() - fit.width() / self._dpr) / 2
        y = rect.y() + (rect.height() - fit.height() / self._dpr) / 2
        painter.save()
        painter.setClipRect(rect)
        painter.drawImage(QPoint(round(x), round(y)), fit)
        painter.restore()

    def _paint_wallpaper(self, painter: QPainter, rect: QRect) -> None:
        opacity = self._theme.wallpaper_opacity
        if self._wallpaper.isNull() or opacity <= 0:
            return
        target = self._device_size()
        if self._wallpaper_fit.isNull() or self._wallpaper_fit.size() != target:
            self._wallpaper_fit = fill_crop(self._wallpaper, target, _FAST)
            self._wallpaper_fit.setDevicePixelRatio(self._dpr)
        painter.setOpacity(opacity)
        painter.drawImage(rect.topLeft(), self._wallpaper_fit)
        painter.setOpacity(1.0)

    # --- стекло ----------------------------------------------------------

    def glass(self) -> QImage:
        """Размытая копия кадра в половинном разрешении (DPR учтён в картинке)."""
        frame = self.frame()
        size = QSize(max(1, frame.width() // 2), max(1, frame.height() // 2))
        if self._glass.isNull() or self._glass.size() != size:
            self._render_glass(frame, size)
        elif self._glass_key != frame.cacheKey() and not self._eco:
            interval = (
                self._video_interval if self.has_video_frame() else GLASS_MIN_INTERVAL
            )
            wait = interval - (monotonic() - self._glass_at)
            if wait <= 0:
                self._render_glass(frame, size)
            elif not self._glass_timer.isActive():
                # кадр больше не меняется — догоним его, когда выйдет интервал
                self._glass_timer.start(max(1, round(wait * 1000)))
        return self._glass

    def _render_glass(self, frame: QImage, size: QSize) -> None:
        half = frame.scaled(size, Qt.AspectRatioMode.IgnoreAspectRatio, _SMOOTH)
        self._glass = blur_image(half, self._theme.glass_blur)
        self._glass.setDevicePixelRatio(frame.devicePixelRatio() / 2)
        self._glass_key = frame.cacheKey()
        self._glass_at = monotonic()

    # --- слой темы -------------------------------------------------------

    def _soft_layer(self) -> QImage:
        if self._soft_dirty or self._soft.isNull():
            self._soft = self._paint_soft()
            self._soft_dirty = False
        return self._soft

    def _paint_soft(self) -> QImage:
        size = self._device_size(0.5)
        image = QImage(size, QImage.Format.Format_RGB32)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = size.width(), size.height()
        rect = QRect(0, 0, w, h)
        backdrop = self._theme.backdrop
        painter.fillRect(rect, qcolor(self._theme.colors.bg))
        depth = QLinearGradient(0, 0, 0, h)
        for pos, color in backdrop.depth:
            depth.setColorAt(pos, qcolor(color))
        painter.fillRect(rect, depth)
        glow = backdrop.glow
        if glow is not None:
            if glow.style == "cover":
                self._paint_cover_glow(painter, w, h)
            else:
                self._paint_spots(painter, w, h, glow)
        if backdrop.vignette is not None:
            vignette = QRadialGradient(rect.center(), max(w, h) * 0.78)
            vignette.setColorAt(0.4, QColor(0, 0, 0, 0))
            vignette.setColorAt(1.0, qcolor(backdrop.vignette))
            painter.fillRect(rect, vignette)
        painter.end()
        return image

    def _paint_spots(self, painter: QPainter, w: int, h: int, glow: GlowSpec) -> None:
        for spot in glow.spots:
            pulse = 0.5 + 0.5 * math.sin(self._phase + spot.phase)
            color = qcolor(spot.rgb)
            gradient = QRadialGradient(w * spot.x, h * spot.y, w * spot.radius)
            color.setAlpha(int(spot.alpha + spot.pulse_alpha * pulse))
            gradient.setColorAt(0.0, color)
            color.setAlpha(0)
            gradient.setColorAt(1.0, color)
            painter.fillRect(0, 0, w, h, gradient)

    def _paint_cover_glow(self, painter: QPainter, w: int, h: int) -> None:
        """Два пятна цветов трека медленно плывут по окну."""
        pulse = 0.5 + 0.5 * math.sin(self._phase)
        pulse2 = 0.5 + 0.5 * math.sin(self._phase + 2.1)
        accent = self._palette.accent
        r, g, b = accent.red(), accent.green(), accent.blue()

        cx = w * (0.78 + 0.06 * math.sin(self._phase * 0.7))
        cy = h * (0.08 + 0.04 * pulse)
        glow = QRadialGradient(cx, cy, w * (0.42 + 0.04 * pulse))
        glow.setColorAt(0.0, QColor(r, g, b, int(36 + 16 * pulse)))
        glow.setColorAt(0.45, QColor(r, g, b, int(12 + 6 * pulse)))
        glow.setColorAt(1.0, QColor(r, g, b, 0))
        painter.fillRect(0, 0, w, h, glow)

        mx = w * (0.12 + 0.05 * math.cos(self._phase * 0.55))
        my = h * (0.85 - 0.05 * pulse2)
        second = self._palette.accent2
        r, g, b = second.red(), second.green(), second.blue()
        coral = QRadialGradient(mx, my, w * (0.38 + 0.05 * pulse2))
        coral.setColorAt(0.0, QColor(r, g, b, int(24 + 10 * pulse2)))
        coral.setColorAt(0.5, QColor(r, g, b, 8))
        coral.setColorAt(1.0, QColor(r, g, b, 0))
        painter.fillRect(0, 0, w, h, coral)


def _with_alpha(color: QColor, alpha: float) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out


def _paint_cinematic_dim(painter: QPainter, rect: QRect) -> None:
    painter.fillRect(rect, QColor(0, 0, 0, 28))
    vignette = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.74)
    vignette.setColorAt(0.0, QColor(0, 0, 0, 0))
    vignette.setColorAt(0.42, QColor(0, 0, 0, 18))
    vignette.setColorAt(0.72, QColor(0, 0, 0, 95))
    vignette.setColorAt(1.0, QColor(0, 0, 0, 175))
    painter.fillRect(rect, vignette)
    top = rect.top() + rect.height() * 0.58
    bottom = QLinearGradient(0, top, 0, rect.bottom())
    bottom.setColorAt(0.0, QColor(0, 0, 0, 0))
    bottom.setColorAt(0.4, QColor(0, 0, 0, 55))
    bottom.setColorAt(1.0, QColor(0, 0, 0, 170))
    painter.fillRect(rect, bottom)
