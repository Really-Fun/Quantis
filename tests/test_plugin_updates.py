"""Проверка обновлений плагинов по магазину."""

from __future__ import annotations

import pytest

from quantis.plugins import updates as updates_module
from quantis.plugins.store import StoreAuthError, StoreError, StorePlugin
from quantis.plugins.updates import PluginUpdates


def _item(plugin_id: str, version: str) -> StorePlugin:
    return StorePlugin(
        plugin_id=plugin_id,
        title=plugin_id,
        version=version,
        description="",
        author="",
        cover_url="",
        download_url=f"https://x/{plugin_id}",
        size=1,
        sha256="0",
    )


class _Registry:
    def __init__(self, versions: dict[str, str]) -> None:
        self.versions = versions

    def installed_version(self, plugin_id: str) -> str | None:
        return self.versions.get(plugin_id)


@pytest.fixture
def make(monkeypatch, qapp):
    def factory(result, versions: dict[str, str]):
        async def fake_fetch(account):
            if isinstance(result, Exception):
                raise result
            return result

        monkeypatch.setattr(updates_module, "fetch_store", fake_fetch)
        checker = PluginUpdates(account=object(), registry=_Registry(versions))
        emitted: list[int] = []
        checker.updates_changed.connect(lambda: emitted.append(len(checker.updates)))
        return checker, emitted

    return factory


@pytest.mark.asyncio
async def test_refresh_counts_only_newer_installed(make) -> None:
    store = [_item("a", "1.1"), _item("b", "1.0"), _item("c", "1.0")]
    checker, emitted = make(store, {"a": "1.0", "b": "1.0"})
    await checker.refresh()
    assert set(checker.updates) == {"a"}
    assert checker.store == store
    assert checker.error == ""
    assert not checker.logged_out
    assert emitted == [1]


@pytest.mark.asyncio
async def test_refresh_logged_out_clears(make, monkeypatch) -> None:
    checker, emitted = make([_item("a", "1.1")], {"a": "1.0"})
    await checker.refresh()

    async def revoked(account):
        raise StoreAuthError("Войдите в аккаунт Quantis")

    monkeypatch.setattr(updates_module, "fetch_store", revoked)
    await checker.refresh()
    assert checker.logged_out
    assert checker.updates == {}
    assert checker.store == []
    assert emitted == [1, 0]


@pytest.mark.asyncio
async def test_refresh_error_keeps_previous_store(make, monkeypatch) -> None:
    store = [_item("a", "1.1")]
    checker, emitted = make(store, {"a": "1.0"})
    await checker.refresh()

    async def down(account):
        raise StoreError("Сервер недоступен")

    monkeypatch.setattr(updates_module, "fetch_store", down)
    await checker.refresh()
    assert checker.error == "Сервер недоступен"
    assert checker.store == store
    assert set(checker.updates) == {"a"}
    assert emitted == [1, 1]


@pytest.mark.asyncio
async def test_recount_after_install(make) -> None:
    registry_versions = {"a": "1.0"}
    checker, emitted = make([_item("a", "1.1")], registry_versions)
    await checker.refresh()
    registry_versions["a"] = "1.1"
    checker.recount()
    assert checker.updates == {}
    assert emitted == [1, 0]
