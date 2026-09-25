"""Загрузка QSS-тем и путей к ресурсам."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QIcon

from quantis.ui.design_tokens import ACCENT_FALLBACK
from quantis.utils import get_asset_path


def ui_theme_labels() -> dict[str, str]:
    """Id темы → название для настроек, в порядке показа."""
    from quantis.ui.themes import registry

    return {theme.id: theme.label for theme in registry.all()}


def styles_dir() -> Path:
    from quantis.utils.resource_path import package_root

    root = package_root()
    for candidate in (root / "styles", root / "quantis" / "styles"):
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parent.parent / "styles"


def icon_path(name: str) -> str:
    return get_asset_path(f"assets/icons/{name}")


_ICON_CACHE: dict[str, QIcon] = {}


def load_icon(name: str) -> QIcon:
    cached = _ICON_CACHE.get(name)
    if cached is not None:
        return cached
    icon = QIcon(icon_path(name))
    _ICON_CACHE[name] = icon
    return icon


def normalize_ui_theme(ui_theme: str | None) -> str:
    from quantis.ui.themes import registry

    return registry.resolve_id(ui_theme)


def wallpaper_path() -> str:
    from quantis.ui.preferences import UiPreferences
    from quantis.ui.wallpapers import resolve_wallpaper_path

    prefs = UiPreferences()
    if not prefs.wallpaper_enabled:
        return ""
    return resolve_wallpaper_path(prefs.wallpaper_path or None)


def dynamic_accent_qss(accent: QColor | None = None) -> str:
    """Runtime-фрагмент QSS с динамическим акцентом из обложки."""
    if accent is None or not accent.isValid():
        accent = QColor(ACCENT_FALLBACK)
    rgb = f"rgb({accent.red()}, {accent.green()}, {accent.blue()})"
    rgba14 = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, 36)"
    rgba40 = f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, 102)"
    return f"""
#controlButton[accent=true] {{
    background: {rgb};
    border-radius: 20px;
}}
#controlButton[accent=true]:hover {{
    background: {rgba40};
}}
#trackTitle[playing="true"] {{ color: {rgb}; }}
#nowPlayingAccent {{ color: {rgb}; }}
#sideNavRail {{ border-color: {rgba14}; }}
#seekSlider::sub-page:horizontal {{
    background: {rgb};
    border-radius: 2px;
}}
#seekSlider::handle:horizontal {{
    border: 2px solid {rgb};
}}
"""


# Правила dynamic_accent_qss, разложенные по виджетам (см. quantis.ui.accent).
# #controlButton[accent=true] не переносим: его background перекрывает
# «background: transparent» на appContent/bodyForeground, он не виден.
# #sideNavRail тоже: его перебивает QFrame#sideNavRail, рельс рисует акцент сам.
ACCENT_TRACK_TITLE_QSS = '#trackTitle[playing="true"] { color: ${rgb}; }'
ACCENT_SEEK_SLIDER_QSS = """
#seekSlider::sub-page:horizontal {
    background: ${rgb};
    border-radius: 2px;
}
#seekSlider::handle:horizontal {
    border: 2px solid ${rgb};
}
"""


def load_stylesheet(
    ui_theme: str | None = None,
    *,
    accent: QColor | None = None,
) -> str:
    """QSS темы; ``accent`` — акцент обложки для правил dynamic_accent_qss."""
    from quantis.ui.themes import qss, registry

    sheet = qss.render(registry.get(ui_theme))
    if accent is None:
        return sheet
    return qss.merge(sheet, dynamic_accent_qss(accent))


def format_ms(ms: int) -> str:
    if ms < 0:
        ms = 0
    total_sec = ms // 1000
    minutes, seconds = divmod(total_sec, 60)
    return f"{minutes}:{seconds:02d}"
