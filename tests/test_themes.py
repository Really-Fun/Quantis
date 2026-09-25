"""Система тем: реестр, полнота описаний, отсутствие id тем вне ui/themes."""

from __future__ import annotations

import ast
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
