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
    """Синхронный мост; корутины, запущенные изнутри другой, идут следом."""

    def __init__(self) -> None:
        self._pending: list = []
        self._running = False

    def schedule(self, coro):
        if self._running:
            self._pending.append(coro)
            return
        self._running = True
        try:
            asyncio.run(coro)
            while self._pending:
                asyncio.run(self._pending.pop(0))
        finally:
            self._running = False

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


def _png() -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    from PySide6.QtGui import QColor, QImage

    image = QImage(32, 18, QImage.Format.Format_RGB32)
    image.fill(QColor("#6C5CE7"))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def test_store_covers_load_once_and_fill_cards(page_env, monkeypatch) -> None:
    from quantis.ui.views.widgets.cover_view import CoverView

    make, registry, updates, *_ = page_env
    fetched: list[str] = []
    png = _png()

    async def fake_fetch(url: str) -> bytes:
        fetched.append(url)
        return png if url.endswith("ok.png") else b""

    monkeypatch.setattr(plugins_page, "fetch_cover", fake_fetch)
    with_cover = _item("cava", "1.0")
    with_cover = with_cover.__class__(
        **{**with_cover.__dict__, "cover_url": "https://x/ok.png"}
    )
    broken = _item("bad", "1.0")
    broken = broken.__class__(**{**broken.__dict__, "cover_url": "https://x/404.png"})
    registry.add("cava", "1.0")
    updates.store = [with_cover, broken, _item("plain", "1.0")]
    page = make()
    page.show_store()
    QApplication.processEvents()

    covers = page.findChildren(CoverView)
    # Карточки магазина + миниатюра установленного cava, у которого есть обложка.
    assert sum(view.has_image for view in covers) == 2
    assert fetched.count("https://x/ok.png") == 1
    page._refresh_all()  # пересборка карточек берёт картинку из кэша
    assert fetched.count("https://x/ok.png") == 1
    page.close()


class _Chunks:
    """Поток aiohttp, который отдаёт тело несколькими кусками."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def iter_chunked(self, _size: int):
        async def gen():
            for chunk in self._chunks:
                yield chunk

        return gen()


def test_read_limited_reads_whole_body_not_first_chunk() -> None:
    body = asyncio.run(
        plugins_page.read_limited(
            _Chunks([b"a" * 16_000, b"b" * 16_000, b"c"]), 100_000
        )
    )
    assert len(body) == 32_001


def test_read_limited_drops_oversized_body() -> None:
    body = asyncio.run(plugins_page.read_limited(_Chunks([b"a" * 60, b"b" * 60]), 100))
    assert body == b""
