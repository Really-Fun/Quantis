"""Сборка QSS темы из общих шаблонов ``styles/templates/*.qss``.

Шаблоны — один набор на все темы, значения через ``${токен}`` (``string.Template``:
в QSS полно фигурных скобок, ``str.format`` не подходит). Каждый селектор в
шаблонах задан ровно один раз. ``ThemeSpec.extra_qss`` сливается с шаблоном по
селекторам: свойства темы дополняют и перекрывают общие, новые селекторы идут
в конец. В итоговом QSS каждый селектор тоже встречается один раз.
"""

from __future__ import annotations

import re
from pathlib import Path
from string import Template

from quantis.ui.themes.spec import ThemeSpec

# Порядок важен: при равной специфичности побеждает правило ниже.
TEMPLATE_FILES = (
    "base",
    "surfaces",
    "panels",
    "home",
    "stats",
    "play_menu",
    "playlist_page",
    "quantis",
    "design",
    "nav_panel",
    "settings",
)

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")

Decls = list[tuple[str, str]]

_CACHE: dict[str, str] = {}
_TEMPLATE: str | None = None


def templates_dir() -> Path:
    from quantis.ui.resources import styles_dir

    return styles_dir() / "templates"


def template_text() -> str:
    global _TEMPLATE
    if _TEMPLATE is None:
        root = templates_dir()
        _TEMPLATE = "\n".join(
            (root / f"{name}.qss").read_text(encoding="utf-8")
            for name in TEMPLATE_FILES
        )
    return _TEMPLATE


def parse(text: str) -> list[tuple[list[str], Decls]]:
    """QSS → [(селекторы, [(свойство, значение)])]; комментарии отбрасываются."""
    rules: list[tuple[list[str], Decls]] = []
    for match in _RULE.finditer(_COMMENT.sub("", text)):
        selectors = [" ".join(s.split()) for s in match.group(1).split(",")]
        selectors = [s for s in selectors if s]
        decls: Decls = []
        for chunk in match.group(2).split(";"):
            name, sep, value = chunk.partition(":")
            if sep and name.strip():
                decls.append((name.strip(), " ".join(value.split())))
        if selectors:
            rules.append((selectors, decls))
    return rules


def _merge_decls(base: Decls, extra: Decls) -> Decls:
    merged = dict(base)
    for name, value in extra:
        merged.pop(name, None)
        merged[name] = value
    return list(merged.items())


def _format(selectors: list[str], decls: Decls) -> str:
    body = "".join(f"    {name}: {value};\n" for name, value in decls)
    return ",\n".join(selectors) + " {\n" + body + "}\n"


def merge(base: str, extra: str) -> str:
    """Шаблон + QSS темы: один блок на селектор."""
    overrides: dict[str, Decls] = {}
    for selectors, decls in parse(extra):
        for sel in selectors:
            overrides[sel] = _merge_decls(overrides.get(sel, []), decls)
    out: list[str] = []
    used: set[str] = set()
    for selectors, decls in parse(base):
        plain = [s for s in selectors if s not in overrides]
        if plain:
            out.append(_format(plain, decls))
        for sel in selectors:
            if sel in overrides:
                out.append(_format([sel], _merge_decls(decls, overrides[sel])))
                used.add(sel)
    for sel, decls in overrides.items():
        if sel not in used:
            out.append(_format([sel], decls))
    return "\n".join(out)


def render(theme: ThemeSpec) -> str:
    cached = _CACHE.get(theme.id)
    if cached is not None:
        return cached
    tokens = theme.tokens()
    base = Template(template_text()).substitute(tokens)
    extra = Template(theme.extra_qss).substitute(tokens)
    sheet = merge(base, extra)
    _CACHE[theme.id] = sheet
    return sheet
