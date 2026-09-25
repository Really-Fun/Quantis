"""Шрифты Quantis: встроенные TTF (``assets/fonts``) и ``QFont`` из ``ThemeFonts``.

Темы задают шрифт списком семейств с запасными (первый в списке часто есть только в
Windows — на Linux побеждает встроенный Manrope). ``QFont.setFamilies`` берёт
первое установленное; родовое семейство в конце списка становится style hint.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from quantis.ui.themes.spec import ThemeSpec
from quantis.utils.resource_path import get_asset_path

logger = logging.getLogger(__name__)

_STYLE_HINTS = {
    "sans-serif": QFont.StyleHint.SansSerif,
    "serif": QFont.StyleHint.Serif,
    "monospace": QFont.StyleHint.Monospace,
}

_registered: tuple[str, ...] | None = None


def fonts_dir() -> Path:
    return Path(get_asset_path("assets/fonts"))


def register_bundled_fonts() -> tuple[str, ...]:
    """Регистрирует TTF из ``assets/fonts`` один раз; нужен созданный QGuiApplication."""
    global _registered
    if _registered is not None:
        return _registered
    families: list[str] = []
    for path in sorted(fonts_dir().glob("*.ttf")):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            logger.warning("Шрифт не загрузился: %s", path.name)
            continue
        for family in QFontDatabase.applicationFontFamilies(font_id):
            if family not in families:
                families.append(family)
    _registered = tuple(families)
    return _registered


def app_font(point_size: float, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """Шрифт приложения (``ui`` активной темы) нужного размера — для значков и глифов."""
    font = QFont(QApplication.font())
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


def theme_font(
    theme: ThemeSpec,
    role: str = "ui",
    point_size: float = 10,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    """``QFont`` роли темы (``ui``, ``display``, ``mono``, ``label``)."""
    families = list(theme.fonts.families(role))
    hint = QFont.StyleHint.AnyStyle
    if families and families[-1] in _STYLE_HINTS:
        hint = _STYLE_HINTS[families.pop()]
    font = QFont()
    font.setFamilies(families)
    font.setStyleHint(hint)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font
