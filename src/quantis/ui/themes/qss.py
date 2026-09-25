"""Сборка QSS темы.

Пока — прежние файлы: базовый (dark/light/yellow_dark), общие widget_styles,
папка темы и settings.qss. Шаблоны с токенами — следующим шагом.
"""

from __future__ import annotations

from quantis.ui.themes.spec import ThemeSpec

_LEGACY_BASE = {"light": "light", "yellow_dark": "yellow_dark"}
_SHARED_WIDGET_STYLES = (
    "surfaces.qss",
    "panels.qss",
    "home.qss",
    "stats.qss",
    "play_menu.qss",
    "playlist_page.qss",
    "playlist_preview.qss",
    "quantis.qss",
    "track_card.qss",
)

_CACHE: dict[str, str] = {}


def render(theme: ThemeSpec) -> str:
    cached = _CACHE.get(theme.id)
    if cached is not None:
        return cached
    from quantis.ui.resources import styles_dir

    root = styles_dir()
    parts = [(root / f"{_LEGACY_BASE.get(theme.id, 'dark')}.qss").read_text("utf-8")]
    widget_dir = root / "widget_styles"
    for name in _SHARED_WIDGET_STYLES:
        path = widget_dir / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    theme_dir = root / "themes" / theme.id
    if theme_dir.is_dir():
        parts.extend(
            p.read_text(encoding="utf-8") for p in sorted(theme_dir.glob("*.qss"))
        )
    settings_qss = widget_dir / "settings.qss"
    if settings_qss.is_file():
        parts.append(settings_qss.read_text(encoding="utf-8"))
    sheet = "\n".join(parts)
    _CACHE[theme.id] = sheet
    return sheet
