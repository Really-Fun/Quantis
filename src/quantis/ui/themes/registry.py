"""Реестр тем: каждый модуль в ``quantis.ui.themes`` с атрибутом ``THEME`` — тема.

Новая тема = новый файл рядом (см. docs/themes.md), регистрировать не нужно.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import fields
from string import Template

from quantis.ui.themes.spec import ThemeSpec

DEFAULT_ID = "neon"

_THEMES: dict[str, ThemeSpec] | None = None


def _discover() -> dict[str, ThemeSpec]:
    import quantis.ui.themes as package

    found: dict[str, ThemeSpec] = {}
    for info in pkgutil.iter_modules(package.__path__):
        if info.name in ("spec", "registry", "qss") or info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}")
        theme = getattr(module, "THEME", None)
        if isinstance(theme, ThemeSpec):
            if theme.id in found:
                raise ValueError(f"тема {theme.id!r} объявлена дважды")
            found[theme.id] = theme
    return dict(sorted(found.items(), key=lambda kv: (kv[1].order, kv[0])))


def _themes() -> dict[str, ThemeSpec]:
    global _THEMES
    if _THEMES is None:
        _THEMES = _discover()
    return _THEMES


def all() -> tuple[ThemeSpec, ...]:  # noqa: A001 — API реестра из задания
    return tuple(_themes().values())


def ids() -> tuple[str, ...]:
    return tuple(_themes())


def default() -> ThemeSpec:
    return _themes()[DEFAULT_ID]


def resolve_id(theme_id: str | None) -> str:
    """Id из настроек → существующая тема (алиасы, иначе тема по умолчанию)."""
    themes = _themes()
    if theme_id in themes:
        return str(theme_id)
    for theme in themes.values():
        if theme_id in theme.aliases:
            return theme.id
    return DEFAULT_ID


def get(theme_id: str | None) -> ThemeSpec:
    return _themes()[resolve_id(theme_id)]


def validate() -> list[str]:
    """Ошибки описаний тем (пустой список — всё в порядке)."""
    from quantis.ui.themes import qss

    errors: list[str] = []
    for theme in all():
        where = f"тема {theme.id!r}"
        for f in fields(theme.colors):
            if not str(getattr(theme.colors, f.name)).strip():
                errors.append(f"{where}: пустой токен {f.name}")
        for role in ("ui", "display", "mono"):
            if not theme.fonts.families(role):
                errors.append(f"{where}: нет шрифтов для {role}")
        if not theme.label.strip():
            errors.append(f"{where}: нет названия")
        try:
            Template(theme.extra_qss).substitute(theme.tokens())
        except (KeyError, ValueError) as exc:
            errors.append(f"{where}: extra_qss — неизвестный токен {exc}")
        try:
            sheet = qss.render(theme)
        except (KeyError, ValueError) as exc:
            errors.append(f"{where}: шаблон QSS — {exc}")
        else:
            if "${" in sheet:
                errors.append(f"{where}: в QSS остался ${{…}}")
    return errors
