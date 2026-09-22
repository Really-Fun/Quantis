"""Dominant color из обложки → dynamic accent (аналог ColorThief)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QImageReader

from quantis.ui.design_tokens import ACCENT_FALLBACK

_FALLBACK = QColor(ACCENT_FALLBACK)


def accent_from_image(image: QImage | None) -> QColor:
    """Грубый histogram dominant color; пропускает слишком тёмные/светлые."""
    if image is None or image.isNull():
        return QColor(_FALLBACK)

    scaled = image
    if image.width() > 64 or image.height() > 64:
        scaled = image.scaled(64, 64)

    buckets: dict[tuple[int, int, int], int] = {}
    for y in range(scaled.height()):
        for x in range(scaled.width()):
            c = scaled.pixelColor(x, y)
            if c.alpha() < 200:
                continue
            # Отсекаем near-black / near-white
            if c.lightness() < 28 or c.lightness() > 230:
                continue
            if c.saturation() < 40:
                continue
            key = (c.red() // 24 * 24, c.green() // 24 * 24, c.blue() // 24 * 24)
            buckets[key] = buckets.get(key, 0) + 1

    if not buckets:
        return QColor(_FALLBACK)

    r, g, b = max(buckets.items(), key=lambda item: item[1])[0]
    color = QColor(r, g, b)
    # Чуть поднимаем насыщенность для UI-акцента
    h, s, v, a = color.getHsv()
    color.setHsv(h, min(255, s + 30), min(255, max(v, 160)), a)
    return color


def accent_from_cover_path(path: str | Path | None) -> QColor:
    if not path:
        return QColor(_FALLBACK)
    file_path = Path(path)
    if not file_path.is_file():
        return QColor(_FALLBACK)
    if file_path.suffix.lower() == ".svg":
        return QColor(_FALLBACK)

    reader = QImageReader(str(file_path))
    reader.setAutoTransform(True)
    original = reader.size()
    if original.isValid():
        reader.setScaledSize(
            original.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio)
        )
    image = reader.read()
    return accent_from_image(image)


def accent_css(color: QColor) -> str:
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"
