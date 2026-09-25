"""Кэшированные ресурсы для делегатов списков треков."""

from __future__ import annotations

from typing import NamedTuple

from PySide6.QtGui import QColor, QFont

# Цвета — Aurora
C_BG_HOVER = QColor(255, 255, 255, 16)
C_BG_PLAYING = QColor(108, 92, 231, 28)
C_BG_ALT = QColor(255, 255, 255, 4)
C_ACCENT = QColor(108, 92, 231)
C_TITLE = QColor(242, 244, 248)
C_TITLE_PLAYING = QColor(108, 92, 231)
C_SUBTITLE = QColor(138, 146, 166)
C_INDEX = QColor(138, 146, 166)
C_INDEX_PLAYING = QColor(108, 92, 231)
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


DARK_PAINT = PaintColors(
    bg_hover=C_BG_HOVER,
    bg_playing=C_BG_PLAYING,
    bg_alt=C_BG_ALT,
    bg_idle=QColor(255, 255, 255, 4),
    title=C_TITLE,
    title_playing=C_TITLE_PLAYING,
    subtitle=C_SUBTITLE,
    index=C_INDEX,
    index_playing=C_INDEX_PLAYING,
    accent=C_ACCENT,
    border=QColor(255, 255, 255, 22),
    border_hover=QColor(108, 92, 231, 70),
    empty=QColor(248, 250, 252, 90),
    meta=QColor(226, 232, 240, 120),
    dl_hover_bg=QColor(255, 255, 255, 16),
    dl_hover_pen=QColor(255, 255, 255, 50),
    dl_hover_text=QColor(248, 250, 252, 200),
)

LIGHT_PAINT = PaintColors(
    bg_hover=QColor(27, 32, 48, 14),
    bg_playing=QColor(108, 92, 231, 28),
    bg_alt=QColor(27, 32, 48, 6),
    bg_idle=QColor(27, 32, 48, 4),
    title=QColor(27, 32, 48),
    title_playing=QColor(108, 92, 231),
    subtitle=QColor(102, 112, 133),
    index=QColor(102, 112, 133),
    index_playing=QColor(108, 92, 231),
    accent=C_ACCENT,
    border=QColor(27, 32, 48, 22),
    border_hover=QColor(108, 92, 231, 70),
    empty=QColor(27, 32, 48, 90),
    meta=QColor(102, 112, 133, 200),
    dl_hover_bg=QColor(27, 32, 48, 10),
    dl_hover_pen=QColor(27, 32, 48, 40),
    dl_hover_text=QColor(27, 32, 48, 200),
)


def paint_colors(theme_id: str | None = None) -> PaintColors:
    from quantis.ui.themes import registry

    if theme_id is None:
        from quantis.ui.preferences import UiPreferences

        theme_id = UiPreferences().ui_theme
    if registry.get(theme_id).is_light:
        return LIGHT_PAINT
    return DARK_PAINT


_UI = "Bahnschrift"
FONT_TITLE = QFont(_UI, 10, QFont.Weight.DemiBold)
FONT_AUTHOR = QFont(_UI, 9)
FONT_INDEX = QFont(_UI, 11, QFont.Weight.Medium)
FONT_PILL = QFont(_UI, 8, QFont.Weight.Bold)
FONT_COVER = QFont(_UI, 11, QFont.Weight.Bold)
FONT_ACTION = QFont(_UI, 10, QFont.Weight.Bold)
FONT_EDITORIAL_TITLE = QFont("Georgia", 12)
FONT_EDITORIAL_AUTHOR = QFont("Cascadia Mono", 8, QFont.Weight.Medium)
FONT_EDITORIAL_INDEX = QFont("Georgia", 28, QFont.Weight.Light)

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
