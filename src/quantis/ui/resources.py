"""Загрузка QSS-тем и путей к ресурсам."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QIcon

from quantis.ui.design_tokens import ACCENT_FALLBACK
from quantis.utils import get_asset_path

THEME_CLASSIC = "classic"
THEME_NEON = "neon"  # Aurora (база)
THEME_AURORA = THEME_NEON
THEME_GLASS = "glass"
THEME_EDITORIAL = "editorial"
THEME_LIGHT = "light"
THEME_YELLOW_DARK = "yellow_dark"
DEFAULT_UI_THEME = THEME_NEON

UI_THEME_LABELS: dict[str, str] = {
    THEME_NEON: "Aurora",
    THEME_GLASS: "Glass",
    THEME_CLASSIC: "Классическая",
    THEME_EDITORIAL: "Редакционная",
    THEME_LIGHT: "Светлая",
    THEME_YELLOW_DARK: "Тёмно-жёлтая",
}

UI_THEME_BASE_QSS: dict[str, str] = {
    THEME_CLASSIC: "dark",
    THEME_NEON: "dark",
    THEME_GLASS: "dark",
    THEME_EDITORIAL: "dark",
    THEME_LIGHT: "light",
    THEME_YELLOW_DARK: "yellow_dark",
}

_SHARED_WIDGET_STYLES = (
    "surfaces.qss",
    "home.qss",
    "stats.qss",
    "play_menu.qss",
    "playlist_page.qss",
    "playlist_preview.qss",
    "quantis.qss",
    "track_card.qss",
)


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
_BASE_SHEET_CACHE: dict[str, str] = {}


def load_icon(name: str) -> QIcon:
    cached = _ICON_CACHE.get(name)
    if cached is not None:
        return cached
    icon = QIcon(icon_path(name))
    _ICON_CACHE[name] = icon
    return icon


def load_theme(theme: str = "dark") -> str:
    theme_file = styles_dir() / f"{theme}.qss"
    if not theme_file.is_file():
        theme_file = styles_dir() / "dark.qss"
    return theme_file.read_text(encoding="utf-8")


def normalize_ui_theme(ui_theme: str | None) -> str:
    if ui_theme in UI_THEME_LABELS:
        return ui_theme
    if ui_theme == "aurora":
        return THEME_NEON
    return DEFAULT_UI_THEME


def load_widget_styles(ui_theme: str = DEFAULT_UI_THEME) -> str:
    theme_id = normalize_ui_theme(ui_theme)
    parts: list[str] = []

    widget_dir = styles_dir() / "widget_styles"
    for name in _SHARED_WIDGET_STYLES:
        if name == "settings.qss":
            continue
        path = widget_dir / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))

    theme_dir = styles_dir() / "themes" / theme_id
    if theme_dir.is_dir():
        for path in sorted(theme_dir.glob("*.qss")):
            parts.append(path.read_text(encoding="utf-8"))

    settings_qss = widget_dir / "settings.qss"
    if settings_qss.is_file():
        parts.append(settings_qss.read_text(encoding="utf-8"))

    return "\n".join(parts)


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


def load_stylesheet(
    ui_theme: str = DEFAULT_UI_THEME,
    *,
    accent: QColor | None = None,
) -> str:
    theme_id = normalize_ui_theme(ui_theme)
    base_sheet = _BASE_SHEET_CACHE.get(theme_id)
    if base_sheet is None:
        base = UI_THEME_BASE_QSS.get(theme_id, "dark")
        base_sheet = load_theme(base) + "\n" + load_widget_styles(theme_id)
        _BASE_SHEET_CACHE[theme_id] = base_sheet
    return base_sheet + "\n" + dynamic_accent_qss(accent)


def format_ms(ms: int) -> str:
    if ms < 0:
        ms = 0
    total_sec = ms // 1000
    minutes, seconds = divmod(total_sec, 60)
    return f"{minutes}:{seconds:02d}"
