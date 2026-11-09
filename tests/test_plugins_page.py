"""Менеджер плагинов: вкладки «Установленные» и «Магазин»."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton

from quantis.plugins.loader import PluginMeta
from quantis.plugins.registry import PluginInfo
from quantis.plugins.store import StoreError, StorePlugin
from quantis.ui.views import plugins_page
from quantis.ui.views.plugins_page import PluginsPage


def _meta(plugin_id: str, version: str, path: Path) -> PluginMeta:
    return PluginMeta(
        plugin_id=plugin_id,
        name=plugin_id.title(),
        version=version,
        author="A",
        description="",
        path=path,
        entry=path / "plugin.py",
    )


def _item(plugin_id: str, version: str) -> StorePlugin:
    return StorePlugin(
        plugin_id=plugin_id,
        title=plugin_id.title(),
        version=version,
        description=f"{plugin_id} desc",
        author="A",
        cover_url="",
        download_url=f"https://x/{plugin_id}",
        size=1,
        sha256="0",
    )


class _Registry(QObject):
    plugin_changed = Signal(str)

    def __init__(self, tmp: Path) -> None:
        super().__init__()
        self.tmp = tmp
        self.infos: dict[str, PluginInfo] = {}
        self.bundled: set[str] = set()
        self.installed: list[tuple[Path, str]] = []
        self.uninstalled: list[str] = []

    def add(
        self,
        plugin_id: str,
        version: str,
        *,
        active: bool = True,
        bundled: bool = False,
    ):
        self.infos[plugin_id] = PluginInfo(
            _meta(plugin_id, version, self.tmp / plugin_id), active
        )
        if bundled:
            self.bundled.add(plugin_id)

    def rescan(self) -> None:
        pass

    def get_all(self):
        return list(self.infos.values())

    def is_bundled(self, plugin_id: str) -> bool:
        return plugin_id in self.bundled

    def installed_version(self, plugin_id: str):
        info = self.infos.get(plugin_id)
        return info.meta.version if info else None

    async def install(self, zip_path: Path, plugin_id: str) -> bool:
        self.installed.append((zip_path, plugin_id))
        self.add(plugin_id, "9.9")
        self.plugin_changed.emit(plugin_id)
        return True

    async def uninstall(self, plugin_id: str) -> None:
        self.uninstalled.append(plugin_id)
        self.infos.pop(plugin_id, None)
        self.plugin_changed.emit(plugin_id)

    async def enable(self, plugin_id: str) -> bool:
        return True

    async def disable(self, plugin_id: str) -> None:
        pass


class _Updates(QObject):
    updates_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.store: list[StorePlugin] = []
        self.updates: dict[str, StorePlugin] = {}
        self.error = ""
        self.logged_out = False
        self.refreshed = 0

    async def refresh(self) -> None:
        self.refreshed += 1
        self.updates_changed.emit()

    def recount(self) -> None:
        self.updates_changed.emit()


class _Account(QObject):
    account_changed = Signal()

    def __init__(self, logged_in: bool = True) -> None:
        super().__init__()
        self.token = "tok" if logged_in else ""

    @property
    def is_logged_in(self) -> bool:
        return bool(self.token)


class _Bridge:
    def schedule(self, coro):
        asyncio.run(coro)

    def invoke_main(self, fn) -> None:
        fn()


@pytest.fixture
def page_env(qapp, tmp_path):
    registry = _Registry(tmp_path)
    updates = _Updates()
    account = _Account()
    notices: list[tuple[str, str, str]] = []
    downloads: list[str] = []
    accounts_opened: list[bool] = []

    async def download(acct, item, dest_dir):
        downloads.append(item.plugin_id)
        if item.plugin_id == "broken":
            raise StoreError("Сервер недоступен")
        path = tmp_path / f"{item.plugin_id}.zip"
        path.write_bytes(b"zip")
        return path

    def make() -> PluginsPage:
        page = PluginsPage(
            _Bridge(),
            account=account,
            updates=updates,
            registry=registry,
            notify=lambda t, m="", k="info": notices.append((t, m, k)),
            download=download,
            open_accounts=lambda: accounts_opened.append(True),
        )
        page.resize(900, 700)
        page.show()
        return page

    yield make, registry, updates, account, notices, downloads, accounts_opened


def _buttons(widget, text: str) -> list[QPushButton]:
    QApplication.processEvents()  # Qt показывает новые виджеты через очередь событий
    return [
        b
        for b in widget.findChildren(QPushButton)
        if b.text() == text and b.isVisible()
    ]


def _labels(widget) -> list[str]:
    QApplication.processEvents()
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisible()]


def test_store_tab_prompts_login_when_logged_out(page_env) -> None:
    make, _, updates, account, _, _, opened = page_env
    account.token = ""
    updates.logged_out = True
    page = make()
    page.show_store()
    assert any("Войдите в аккаунт Quantis" in text for text in _labels(page))
    _buttons(page, "Открыть аккаунты")[0].click()
    assert opened == [True]
    page.close()


def test_store_buttons_follow_store_action(page_env) -> None:
    make, registry, updates, _, _, _, _ = page_env
    registry.add("old", "1.0")
    registry.add("same", "1.0")
    updates.store = [_item("new", "1.0"), _item("old", "1.1"), _item("same", "1.0")]
    page = make()
    page.show_store()
    assert len(_buttons(page, "Установить")) == 1
    assert len(_buttons(page, "Обновить")) == 1
    installed = _buttons(page, "Установлено")
    assert len(installed) == 1 and not installed[0].isEnabled()
    page.close()


def test_install_click_downloads_and_installs(page_env) -> None:
    make, registry, updates, _, notices, downloads, _ = page_env
    updates.store = [_item("new", "1.0")]
    page = make()
    page.show_store()
    _buttons(page, "Установить")[0].click()
    assert downloads == ["new"]
    assert [pid for _, pid in registry.installed] == ["new"]
    assert notices[-1] == ("Плагин «New» установлен", "", "success")
    assert not registry.installed[0][0].exists()  # скачанный zip убран
    page.close()


def test_update_button_on_installed_tab(page_env) -> None:
    make, registry, updates, _, notices, downloads, _ = page_env
    registry.add("old", "1.0")
    updates.store = [_item("old", "1.1")]
    updates.updates = {"old": updates.store[0]}
    page = make()
    page.show_installed()
    _buttons(page, "Обновить до v1.1")[0].click()
    assert downloads == ["old"]
    assert notices[-1] == ("Плагин «Old» обновлён до v1.1", "", "success")
    page.close()


def test_bundled_has_no_delete_button(page_env) -> None:
    make, registry, _, _, _, _, _ = page_env
    registry.add("core", "1.0", bundled=True)
    registry.add("mine", "1.0")
    page = make()
    page.show_installed()
    assert len(_buttons(page, "Удалить")) == 1
    page.close()


def test_delete_asks_confirmation(page_env, monkeypatch) -> None:
    make, registry, _, _, _, _, _ = page_env
    registry.add("mine", "1.0")
    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(
        plugins_page.QMessageBox, "question", lambda *a, **k: answers.pop(0)
    )
    page = make()
    page.show_installed()
    _buttons(page, "Удалить")[0].click()
    assert registry.uninstalled == []
    _buttons(page, "Удалить")[0].click()
    assert registry.uninstalled == ["mine"]
    page.close()


def test_install_error_notifies(page_env) -> None:
    make, registry, updates, _, notices, _, _ = page_env
    updates.store = [_item("broken", "1.0")]
    page = make()
    page.show_store()
    button = _buttons(page, "Установить")[0]
    button.click()
    assert notices[-1] == (
        "Не удалось установить «Broken»",
        "Сервер недоступен",
        "error",
    )
    assert registry.installed == []
    assert _buttons(page, "Установить")[0].isEnabled()
    page.close()


def test_store_error_shows_retry(page_env) -> None:
    make, _, updates, _, _, _, _ = page_env
    updates.error = "Сервер недоступен: https://x"
    page = make()
    page.show_store()
    assert any("Сервер недоступен" in text for text in _labels(page))
    before = updates.refreshed
    _buttons(page, "Повторить")[0].click()
    assert updates.refreshed == before + 1
    page.close()


def test_showing_page_refreshes_store(page_env) -> None:
    make, _, updates, _, _, _, _ = page_env
    page = make()
    assert updates.refreshed >= 1
    page.close()


def test_no_download_by_url_button(page_env) -> None:
    make, *_ = page_env
    page = make()
    assert _buttons(page, "Скачать по URL") == []
    assert _buttons(page, "Импорт из архива")
    page.close()
