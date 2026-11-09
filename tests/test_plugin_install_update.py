"""Установка, обновление с откатом и удаление плагинов без перезапуска."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

from quantis.plugins.installer import PluginInstallError
from quantis.plugins.loader import PluginLoader
from quantis.plugins.registry import PluginRegistry

PLUGIN_SRC = """
from quantis.plugins.base import BasePlugin
import helper

class Demo(BasePlugin):
    async def on_load(self):
        {on_load}
        self.host.loaded.append(helper.VERSION)

    async def on_unload(self):
        self.host.unloaded.append(helper.VERSION)
"""


def plugin_files(
    version: str,
    *,
    plugin_id: str = "demo",
    on_load: str = "pass",
    broken: bool = False,
) -> dict[str, str]:
    return {
        "plugin.py": PLUGIN_SRC.format(on_load=on_load),
        # Второй модуль по короткому имени — как client.py/page.py у Together.
        "helper.py": ("raise RuntimeError('сломано')\n" if broken else "")
        + f"VERSION = {version!r}\n",
        "manifest.json": json.dumps(
            {"id": plugin_id, "name": "Demo", "version": version}
        ),
    }


def make_zip(
    tmp_path: Path, files: dict[str, str], name: str = "demo.zip", folder: str = "demo"
) -> Path:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for rel, data in files.items():
            zf.writestr(f"{folder}/{rel}" if folder else rel, data)
    path = tmp_path / name
    path.write_bytes(buf.getvalue())
    return path


def write_plugin(folder: Path, files: dict[str, str]) -> None:
    folder.mkdir(parents=True)
    for rel, data in files.items():
        (folder / rel).write_text(data, encoding="utf-8")


class _Host:
    def __init__(self) -> None:
        self.loaded: list[str] = []
        self.unloaded: list[str] = []


@pytest.fixture
def env(tmp_path, qapp):
    user = tmp_path / "user_plugins"
    bundled = tmp_path / "bundled_plugins"
    user.mkdir()
    bundled.mkdir()
    settings = QSettings(str(tmp_path / "plugins.ini"), QSettings.Format.IniFormat)
    registry = PluginRegistry(
        loader=PluginLoader(dirs=[user, bundled]), settings=settings
    )
    host = _Host()
    return registry, host, user, bundled, tmp_path


async def _start(registry: PluginRegistry, host: _Host) -> None:
    await registry.load_all(host)


@pytest.mark.asyncio
async def test_install_new_plugin_enables_it(env) -> None:
    registry, host, user, _, tmp = env
    await _start(registry, host)
    assert await registry.install(make_zip(tmp, plugin_files("1")), "demo")
    assert registry.is_active("demo")
    assert registry.installed_version("demo") == "1"
    assert host.loaded == ["1"]
    assert (user / "demo" / "plugin.py").is_file()


@pytest.mark.asyncio
async def test_install_rejects_id_mismatch(env) -> None:
    registry, host, user, _, tmp = env
    await _start(registry, host)
    archive = make_zip(tmp, plugin_files("1", plugin_id="other"))
    with pytest.raises(PluginInstallError, match="не совпадает"):
        await registry.install(archive, "demo")
    assert not (user / "demo").exists()
    assert registry.installed_version("demo") is None


@pytest.mark.asyncio
async def test_update_active_plugin_reloads_new_code(env) -> None:
    registry, host, user, _, tmp = env
    await _start(registry, host)
    await registry.install(make_zip(tmp, plugin_files("1")), "demo")
    plugin_settings = QSettings("ReallyFun", "Quantis/plugins/demo")
    plugin_settings.setValue("keep", "me")
    assert await registry.install(
        make_zip(tmp, plugin_files("2"), name="v2.zip"), "demo"
    )
    assert host.loaded == ["1", "2"]  # загружен код новой версии, а не старый модуль
    assert host.unloaded == ["1"]
    assert registry.is_active("demo")
    assert registry.installed_version("demo") == "2"
    assert sorted(p.name for p in user.iterdir()) == ["demo"]  # бэкапа не осталось
    assert QSettings("ReallyFun", "Quantis/plugins/demo").value("keep") == "me"
    plugin_settings.remove("keep")


@pytest.mark.asyncio
async def test_update_rolls_back_when_new_version_fails(env) -> None:
    registry, host, user, _, tmp = env
    await _start(registry, host)
    await registry.install(make_zip(tmp, plugin_files("1")), "demo")
    broken = make_zip(tmp, plugin_files("2", broken=True), name="v2.zip")
    assert not await registry.install(broken, "demo")
    assert registry.is_active("demo")
    assert registry.installed_version("demo") == "1"
    assert host.loaded == ["1", "1"]
    assert "VERSION = '1'" in (user / "demo" / "helper.py").read_text()
    assert sorted(p.name for p in user.iterdir()) == ["demo"]


@pytest.mark.asyncio
async def test_update_rolls_back_when_on_load_raises(env) -> None:
    registry, host, _, _, tmp = env
    await _start(registry, host)
    await registry.install(make_zip(tmp, plugin_files("1")), "demo")
    bad = make_zip(
        tmp, plugin_files("2", on_load="raise RuntimeError('boom')"), name="v2.zip"
    )
    assert not await registry.install(bad, "demo")
    assert registry.installed_version("demo") == "1"
    assert registry.is_active("demo")


@pytest.mark.asyncio
async def test_update_of_disabled_plugin_stays_disabled(env) -> None:
    registry, host, _, _, tmp = env
    await _start(registry, host)
    await registry.install(make_zip(tmp, plugin_files("1")), "demo")
    await registry.disable("demo")
    assert await registry.install(
        make_zip(tmp, plugin_files("2"), name="v2.zip"), "demo"
    )
    assert not registry.is_active("demo")
    assert registry.installed_version("demo") == "2"


@pytest.mark.asyncio
async def test_uninstall_removes_folder_and_info(env) -> None:
    registry, host, user, _, tmp = env
    await _start(registry, host)
    await registry.install(make_zip(tmp, plugin_files("1")), "demo")
    await registry.uninstall("demo")
    assert not (user / "demo").exists()
    assert registry.get_info("demo") is None
    assert host.unloaded == ["1"]


@pytest.mark.asyncio
async def test_bundled_plugin_cannot_be_uninstalled(env) -> None:
    registry, host, _, bundled, _ = env
    write_plugin(bundled / "demo", plugin_files("1"))
    await _start(registry, host)
    assert registry.is_bundled("demo")
    with pytest.raises(PluginInstallError):
        await registry.uninstall("demo")
    assert (bundled / "demo").exists()


@pytest.mark.asyncio
async def test_user_copy_shadows_bundled(env) -> None:
    registry, host, user, bundled, tmp = env
    write_plugin(bundled / "demo", plugin_files("1"))
    await _start(registry, host)
    await registry.install(make_zip(tmp, plugin_files("2")), "demo")
    assert registry.installed_version("demo") == "2"
    assert not registry.is_bundled("demo")
    assert (user / "demo").is_dir() and (bundled / "demo").is_dir()


def test_backup_dirs_are_not_discovered(tmp_path) -> None:
    write_plugin(tmp_path / "_backup_demo", plugin_files("1"))
    write_plugin(tmp_path / "_new_demo", plugin_files("2"))
    assert PluginLoader(tmp_path).discover() == []
