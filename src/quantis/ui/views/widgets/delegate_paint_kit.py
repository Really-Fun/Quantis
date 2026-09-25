"""Кэшированные ресурсы для делегатов списков треков."""

from __future__ import annotations

from typing import NamedTuple

from PySide6.QtGui import QColor, QFont, QFontMetrics

from quantis.ui.themes.spec import ThemeSpec, qcolor

# Бейджи источников — одинаковые во всех темах
C_YT = QColor(255, 78, 69)
C_YA = QColor(255, 219, 77)
C_SC = QColor(255, 119, 0)
C_PILL_TEXT = QColor(20, 22, 28)


class PaintColors(NamedTuple):
    bg_hover: QColor
    bg_playing: QColor
    bg_alt: QColor
    bg_idle: QColor
    title: QColor
    title_playing: QColor
    subtitle: QColor
    index: QColor
    index_playing: QColor
    accent: QColor
    border: QColor
    border_hover: QColor
    empty: QColor
    meta: QColor
    dl_hover_bg: QColor
    dl_hover_pen: QColor
    dl_hover_text: QColor


def _with_alpha(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(alpha)
    return out


def build_paint_colors(theme: ThemeSpec, accent: QColor) -> PaintColors:
    """Палитра делегатов из токенов темы и текущего акцента обложки."""
    c = theme.colors
    ink = qcolor(c.ink_rgb)
    title = qcolor(c.title)
    meta = qcolor(c.text_meta)
    return PaintColors(
        bg_hover=_with_alpha(ink, 16),
        bg_playing=_with_alpha(accent, 28),
        bg_alt=_with_alpha(ink, 4),
        bg_idle=_with_alpha(ink, 4),
        title=qcolor(c.text),
        title_playing=QColor(accent),
        subtitle=meta,
        index=meta,
        index_playing=QColor(accent),
        accent=QColor(accent),
        border=_with_alpha(ink, 22),
        border_hover=_with_alpha(accent, 70),
        empty=_with_alpha(title, 90),
        meta=_with_alpha(qcolor(c.mist_rgb), 120),
        dl_hover_bg=_with_alpha(ink, 16),
        dl_hover_pen=_with_alpha(ink, 50),
        dl_hover_text=_with_alpha(title, 200),
    )


_PAINT_CACHE: dict[tuple[str, int], PaintColors] = {}


def paint_colors(theme: ThemeSpec | None = None) -> PaintColors:
    """Палитра текущей темы (или ``theme``) с текущим акцентом."""
    from quantis.ui.accent import AccentStyles

    if theme is None:
        from quantis.ui.preferences import UiPreferences

        theme = UiPreferences().theme
    accent = AccentStyles.instance().color
    key = (theme.id, accent.rgba())
    cached = _PAINT_CACHE.get(key)
    if cached is None:
        cached = build_paint_colors(theme, accent)
        _PAINT_CACHE[key] = cached
    return cached


class PaintFonts(NamedTuple):
    title: QFont
    author: QFont
    index: QFont
    cover: QFont
    action: QFont
    editorial_title: QFont
    editorial_author: QFont
    editorial_index: QFont
    fm_title: QFontMetrics
    fm_author: QFontMetrics
    fm_editorial_title: QFontMetrics
    fm_editorial_author: QFontMetrics


def build_paint_fonts(theme: ThemeSpec) -> PaintFonts:
    """Шрифты делегатов из ``ThemeFonts``: списки с запасными, а не имя из Windows."""
    from quantis.ui.fonts import theme_font

    w = QFont.Weight
    title = theme_font(theme, "ui", 10, w.DemiBold)
    author = theme_font(theme, "ui", 9)
    editorial_title = theme_font(theme, "display", 12)
    editorial_author = theme_font(theme, "label", 8, w.Medium)
    return PaintFonts(
        title=title,
        author=author,
        index=theme_font(theme, "ui", 11, w.Medium),
        cover=theme_font(theme, "ui", 11, w.Bold),
        action=theme_font(theme, "ui", 10, w.Bold),
        editorial_title=editorial_title,
        editorial_author=editorial_author,
        editorial_index=theme_font(theme, "display", 28, w.Light),
        fm_title=QFontMetrics(title),
        fm_author=QFontMetrics(author),
        fm_editorial_title=QFontMetrics(editorial_title),
        fm_editorial_author=QFontMetrics(editorial_author),
    )


_FONT_CACHE: dict[str, PaintFonts] = {}


def paint_fonts(theme: ThemeSpec | None = None) -> PaintFonts:
    """Шрифты текущей темы (или ``theme``); кэш по id темы."""
    if theme is None:
        from quantis.ui.preferences import UiPreferences

        theme = UiPreferences().theme
    cached = _FONT_CACHE.get(theme.id)
    if cached is None:
        cached = build_paint_fonts(theme)
        _FONT_CACHE[theme.id] = cached
    return cached


SOURCE_LABELS = {
    "youtube": "YT",
    "yandex": "YA",
    "soundcloud": "SC",
}

SOURCE_COLORS = {
    "youtube": C_YT,
    "yandex": C_YA,
    "soundcloud": C_SC,
}
