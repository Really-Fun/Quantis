"""Цвета из обложки: палитра трека (``CoverPalette``) и старый dominant color."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QImageReader

from quantis.ui.themes.spec import ThemeSpec, qcolor

_NONE = QColor()


@dataclass(frozen=True, eq=False)
class CoverPalette:
    """Три цвета трека: акцент, второй акцент другого оттенка, глубокий тон фона."""

    accent: QColor
    accent2: QColor
    deep: QColor

    def lerp(self, other: CoverPalette, t: float) -> CoverPalette:
        return CoverPalette(
            lerp_color(self.accent, other.accent, t),
            lerp_color(self.accent2, other.accent2, t),
            lerp_color(self.deep, other.deep, t),
        )

    def _key(self) -> tuple[int, int, int]:
        return (self.accent.rgba(), self.accent2.rgba(), self.deep.rgba())

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CoverPalette):
            return NotImplemented
        return self._key() == other._key()

    def __hash__(self) -> int:
        return hash(self._key())


def lerp_color(a: QColor, b: QColor, t: float) -> QColor:
    return QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


def _hue_gap(a: float, b: float) -> float:
    d = abs(a - b)
    return min(d, 1 - d)


def palette_from_image(image: QImage | None) -> CoverPalette | None:
    """Палитра по сетке 6×6: самый насыщенный тон — акцент, следующий заметно
    другой оттенок — второй акцент. Почти ч/б картинка — нейтральная холодная
    палитра. Нет картинки — ``None`` (запасную выбирает вызывающий по теме)."""
    if image is None or image.isNull():
        return None
    small = image.scaled(
        6,
        6,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    px: list[tuple[float, float, float]] = []
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            s, v = c.hsvSaturationF(), c.valueF()
            px.append((s * v, max(c.hsvHueF(), 0.0), s))
    px.sort(key=lambda item: -item[0])
    if px[0][2] < 0.12:
        return CoverPalette(
            QColor.fromHsvF(0.7, 0.18, 1.0),
            QColor.fromHsvF(0.58, 0.2, 0.95),
            QColor.fromHsvF(0.7, 0.3, 0.3),
        )
    h1 = px[0][1]
    h2 = next(
        (h for _, h, s in px[1:] if s > 0.25 and _hue_gap(h, h1) > 0.07),
        (h1 + 0.09) % 1.0,
    )
    return CoverPalette(
        QColor.fromHsvF(h1, 0.72, 1.0),
        QColor.fromHsvF(h2, 0.68, 0.98),
        QColor.fromHsvF(h1, 0.8, 0.42),
    )


def palette_from_accent(color: QColor) -> CoverPalette:
    """Палитра из одного цвета (акцент темы без обложки): соседний оттенок и
    глубокий тон того же цвета."""
    h, s, v = max(color.hsvHueF(), 0.0), color.hsvSaturationF(), color.valueF()
    return CoverPalette(
        QColor(color),
        QColor.fromHsvF((h + 0.09) % 1.0, min(1.0, s * 0.95), max(v, 0.6)),
        QColor.fromHsvF(h, min(1.0, s + 0.1), min(v, 0.42)),
    )


def fallback_palette(theme: ThemeSpec | None = None) -> CoverPalette:
    return palette_from_accent(fallback_accent(theme))


def fallback_accent(theme: ThemeSpec | None = None) -> QColor:
    """Акцент темы, пока нет обложки (``ThemeColors.accent_fallback``)."""
    if theme is None:
        from quantis.ui.preferences import UiPreferences

        theme = UiPreferences().theme
    return qcolor(theme.colors.accent_fallback)


def accent_from_image(image: QImage | None) -> QColor:
    """Грубый histogram dominant color; пропускает слишком тёмные/светлые.

    Не нашлось цвета — невалидный ``QColor``: запасной акцент выбирает вызывающий
    (см. ``fallback_accent``), он зависит от темы.
    """
    if image is None or image.isNull():
        return QColor(_NONE)

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
        return QColor(_NONE)

    r, g, b = max(buckets.items(), key=lambda item: item[1])[0]
    color = QColor(r, g, b)
    # Чуть поднимаем насыщенность для UI-акцента
    color.setHsv(
        color.hsvHue(),
        min(255, color.hsvSaturation() + 30),
        min(255, max(color.value(), 160)),
        color.alpha(),
    )
    return color


def load_cover_image(path: str | Path | None) -> QImage | None:
    """Обложка с диска, уменьшенная до 96 px: на палитру и мягкий фон хватает."""
    if not path:
        return None
    file_path = Path(path)
    if not file_path.is_file() or file_path.suffix.lower() == ".svg":
        return None
    reader = QImageReader(str(file_path))
    reader.setAutoTransform(True)
    original = reader.size()
    if original.isValid():
        reader.setScaledSize(
            original.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio)
        )
    image = reader.read()
    return None if image.isNull() else image


def accent_from_cover_path(path: str | Path | None) -> QColor:
    return accent_from_image(load_cover_image(path))


def palette_from_cover_path(path: str | Path | None) -> CoverPalette | None:
    return palette_from_image(load_cover_image(path))


def accent_css(color: QColor) -> str:
    return f"rgb({color.red()}, {color.green()}, {color.blue()})"
