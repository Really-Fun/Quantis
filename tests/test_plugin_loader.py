"""Изоляция импортов соседних модулей плагинов (page.py и т.п.)."""

from __future__ import annotations

from pathlib import Path

from quantis.plugins.loader import PluginLoader, PluginMeta


def _write_plugin(root: Path, plugin_id: str, page_value: str) -> PluginMeta:
    folder = root / plugin_id
    folder.mkdir()
    (folder / "manifest.json").write_text(
        f'{{"id": "{plugin_id}", "name": "{plugin_id}", "version": "1.0.0"}}',
        encoding="utf-8",
    )
    (folder / "page.py").write_text(
        f"VALUE = {page_value!r}\n",
        encoding="utf-8",
    )
    (folder / "plugin.py").write_text(
        "from page import VALUE\n"
        "from quantis.plugins.base import BasePlugin\n"
        "\n"
        f"class {plugin_id.title().replace('_', '')}Plugin(BasePlugin):\n"
        f"    name = {plugin_id!r}\n"
        "    marker = VALUE\n",
        encoding="utf-8",
    )
    return PluginMeta(
        plugin_id=plugin_id,
        name=plugin_id,
        version="1.0.0",
        author="test",
        description="",
        path=folder,
        entry=folder / "plugin.py",
    )


def test_second_plugin_does_not_import_first_plugin_page(tmp_path: Path) -> None:
    cava = _write_plugin(tmp_path, "cava_like", "cava-page")
    together = _write_plugin(tmp_path, "together_like", "together-page")
    loader = PluginLoader(tmp_path)

    cava_cls = loader.load_class(cava)
    together_cls = loader.load_class(together)

    assert cava_cls.marker == "cava-page"
    assert together_cls.marker == "together-page"


def test_plugin_relative_page_import(tmp_path: Path) -> None:
    folder = tmp_path / "relplug"
    folder.mkdir()
    (folder / "page.py").write_text("VALUE = 'relative'\n", encoding="utf-8")
    (folder / "plugin.py").write_text(
        "from .page import VALUE\n"
        "from quantis.plugins.base import BasePlugin\n"
        "\n"
        "class RelPlugin(BasePlugin):\n"
        "    name = 'rel'\n"
        "    marker = VALUE\n",
        encoding="utf-8",
    )
    meta = PluginMeta(
        plugin_id="relplug",
        name="relplug",
        version="1.0.0",
        author="test",
        description="",
        path=folder,
        entry=folder / "plugin.py",
    )
    cls = PluginLoader(tmp_path).load_class(meta)
    assert cls.marker == "relative"
