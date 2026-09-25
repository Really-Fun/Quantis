"""Шрифты: встроенные TTF, списки с запасными из ThemeFonts, без имён из Windows."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtGui import QFontInfo

import quantis
from quantis.ui.fonts import register_bundled_fonts, theme_font
from quantis.ui.themes import registry
from quantis.ui.views.widgets.delegate_paint_kit import paint_fonts

SRC = Path(quantis.__file__).parent
THEMES_DIR = SRC / "ui" / "themes"

_WINDOWS_FONTS = re.compile(r"Bahnschrift|Segoe UI|Georgia|Cascadia Mono|Consolas")


def test_bundled_fonts_register(qapp) -> None:
    families = register_bundled_fonts()
    assert "Manrope" in families
    assert "Unbounded" in families


def test_theme_font_falls_back_to_bundled(qapp) -> None:
    register_bundled_fonts()
    font = theme_font(registry.get("neon"), "ui", 10)
    assert font.families()[0] == "Bahnschrift"
    installed = QFontInfo(font).family()
    # на Windows победит Bahnschrift, в остальных системах — встроенный Manrope
    assert installed in {"Bahnschrift", "Manrope"}


def test_generic_family_becomes_style_hint(qapp) -> None:
    font = theme_font(registry.get("editorial"), "display", 12)
    assert "serif" not in font.families()
    assert font.styleHint() == font.StyleHint.Serif


def test_paint_fonts_follow_theme(qapp) -> None:
    editorial = paint_fonts(registry.get("editorial"))
    neon = paint_fonts(registry.get("neon"))
    assert editorial.editorial_title.families()[0] == "Georgia"
    assert neon.title.families() != editorial.title.families()


def test_no_windows_font_names_outside_themes() -> None:
    """Семейства шрифтов задаёт ThemeFonts; виджеты берут QFont из темы."""
    offenders = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*"))
        if path.suffix in {".py", ".qss"}
        and THEMES_DIR not in path.parents
        and _WINDOWS_FONTS.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
