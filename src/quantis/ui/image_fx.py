"""Дешёвые операции с картинками для фона: заполнение, размытие, яркость."""

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QImage

_SMOOTH = Qt.TransformationMode.SmoothTransformation
_IGNORE = Qt.AspectRatioMode.IgnoreAspectRatio


def fill_crop(
    image: QImage,
    size: QSize,
    mode: Qt.TransformationMode = _SMOOTH,
) -> QImage:
    """Как ``background-size: cover``: заполнить ``size`` без полос, лишнее
    обрезать по центру. Сначала вырезаем, потом масштабируем — меньше работы."""
    w, h = size.width(), size.height()
    iw, ih = image.width(), image.height()
    if image.isNull() or w <= 0 or h <= 0 or iw <= 0 or ih <= 0:
        return QImage()
    scale = max(w / iw, h / ih)
    cw, ch = w / scale, h / scale
    src = QRect(
        int((iw - cw) / 2), int((ih - ch) / 2), max(1, int(cw)), max(1, int(ch))
    )
    return image.copy(src).scaled(w, h, _IGNORE, mode)


def blur_image(image: QImage, amount: float) -> QImage:
    """Дешёвое размытие: уменьшаем (усреднение по площади) и увеличиваем
    ступенями ×2. ``amount`` 0..1 → уменьшение в 1..40 раз."""
    if amount <= 0.01 or image.isNull():
        return image
    w, h = image.width(), image.height()
    factor = 1 + amount * 39
    small = image.scaled(
        max(2, int(w / factor)), max(2, int(h / factor)), _IGNORE, _SMOOTH
    )
    while small.width() * 2 < w:
        small = small.scaled(small.width() * 2, small.height() * 2, _IGNORE, _SMOOTH)
    out = small.scaled(w, h, _IGNORE, _SMOOTH)
    out.setDevicePixelRatio(image.devicePixelRatio())
    return out


def mean_luma(image: QImage) -> float:
    """Средняя яркость 0..1 по сетке 8×8."""
    if image.isNull():
        return 0.0
    small = image.scaled(8, 8, _IGNORE, _SMOOTH)
    total = 0.0
    for y in range(8):
        for x in range(8):
            c = small.pixelColor(x, y)
            total += 0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()
    return total / 64
