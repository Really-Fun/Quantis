"""Система тем: реестр, полнота описаний, отсутствие id тем вне ui/themes."""

from __future__ import annotations

import ast
import re
from dataclasses import fields
from pathlib import Path

import pytest

import quantis
from quantis.ui.themes import registry
from quantis.ui.themes.spec import ThemeColors

SRC = Path(quantis.__file__).parent
THEMES_DIR = SRC / "ui" / "themes"


def test_registry_has_themes_and_default() -> None:
    ids = registry.ids()
    for theme_id in ("neon", "glass", "classic", "editorial", "light", "yellow_dark"):
        assert theme_id in ids
    assert registry.default().id == registry.DEFAULT_ID


def test_saved_ids_resolve() -> None:
    assert registry.get("aurora").id == "neon"  # алиас из старых настроек
    assert registry.get("no-such-theme").id == registry.DEFAULT_ID
    assert registry.get(None).id == registry.DEFAULT_ID


def test_validate_is_clean() -> None:
    assert registry.validate() == []


@pytest.mark.parametrize("theme", registry.all(), ids=lambda t: t.id)
def test_theme_tokens_filled(theme) -> None:
    for f in fields(ThemeColors):
        assert str(getattr(theme.colors, f.name)).strip(), f.name
    assert theme.fonts.families("ui")
    assert theme.label


def _theme_literals() -> set[str]:
    names: set[str] = set()
    for theme in registry.all():
        names.add(theme.id)
        names.update(theme.aliases)
    return names


def test_no_theme_ids_outside_themes_package() -> None:
    """Поведение темы — поля ThemeSpec, а не `if theme == "glass"`."""
    literals = _theme_literals()
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if THEMES_DIR in path.parents:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and node.value in literals:
                offenders.append(
                    f"{path.relative_to(SRC)}:{node.lineno} {node.value!r}"
                )
    assert offenders == []


def test_template_selectors_defined_once() -> None:
    from string import Template

    from quantis.ui.themes import qss

    tokens = registry.default().tokens()
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    for name in qss.TEMPLATE_FILES:
        raw = (qss.templates_dir() / f"{name}.qss").read_text(encoding="utf-8")
        text = Template(raw).substitute(tokens)
        for selectors, _decls in qss.parse(text):
            for sel in selectors:
                if sel in seen:
                    duplicates.append(f"{sel}: {seen[sel]} и {name}")
                seen[sel] = name
    assert duplicates == []


@pytest.mark.parametrize("theme", registry.all(), ids=lambda t: t.id)
def test_rendered_qss_complete(theme) -> None:
    from quantis.ui.themes import qss

    sheet = qss.render(theme)
    assert "${" not in sheet
    selectors = [s for sels, _ in qss.parse(sheet) for s in sels]
    assert len(selectors) == len(set(selectors))


def test_extra_qss_overrides_template() -> None:
    from quantis.ui.themes import qss

    merged = qss.merge(
        "#a,\n#b {\n    color: red;\n    margin: 0;\n}\n",
        "#b { color: blue; }\n#c { x: 1; }",
    )
    rules = {s: dict(d) for sels, d in qss.parse(merged) for s in sels}
    assert rules["#a"] == {"color": "red", "margin": "0"}
    assert rules["#b"] == {"color": "blue", "margin": "0"}
    assert rules["#c"] == {"x": "1"}


def test_packaging_collects_all_templates() -> None:
    import importlib.util

    root = Path(quantis.__file__).parents[2]
    spec = importlib.util.spec_from_file_location(
        "quantis_collect_datas", root / "packaging" / "pyinstaller" / "collect_datas.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from quantis.ui.themes import qss

    items = mod.collect_styles(qss.templates_dir().parent)
    collected = {Path(src).name for src, dest in items if dest.endswith("templates")}
    assert collected == {f"{name}.qss" for name in qss.TEMPLATE_FILES}


def test_settings_combo_lists_all_themes(qapp) -> None:
    from quantis.ui.views.settings_page import SettingsPage

    page = SettingsPage()
    combo = page._theme_combo
    listed = [combo.itemData(i) for i in range(combo.count())]
    assert listed == list(registry.ids())


_PURPLE = re.compile(r"108,\s*92,\s*231|#6C5CE7", re.I)


def test_no_hardcoded_purple_outside_theme_colors() -> None:
    """Фиолетовый — значение темы (ThemeColors), а не литерал в QSS и виджетах."""
    offenders = []
    for path in sorted(SRC.rglob("*")):
        if path.suffix not in {".py", ".qss"} or path.name == "design_tokens.py":
            continue
        text = path.read_text(encoding="utf-8")
        if path.parent == THEMES_DIR:
            # в модуле темы фиолетовый допустим только в ThemeColors(...)
            text = text.partition("THEME = ")[0]
        if _PURPLE.search(text):
            offenders.append(str(path.relative_to(SRC)))
    assert offenders == []


def test_no_cover_accent_follows_theme(qapp, tmp_path) -> None:
    from quantis.ui.cover_accent import accent_from_cover_path, fallback_accent

    assert not accent_from_cover_path(None).isValid()
    assert not accent_from_cover_path(tmp_path / "missing.jpg").isValid()
    yellow = registry.get("yellow_dark")
    assert fallback_accent(yellow).name().upper() == yellow.colors.accent_fallback
