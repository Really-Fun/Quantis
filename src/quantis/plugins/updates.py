"""Что есть в магазине и какие установленные плагины можно обновить.

Один объект на окно: питает бейдж «Менеджера плагинов» в левой панели и
вкладку «Магазин». ``refresh`` зовут при старте, при смене аккаунта и при
открытии менеджера; ``recount`` — после установки или удаления.
"""

from __future__ import annotations

import logging
from typing import Protocol

from PySide6.QtCore import QObject, Signal

from quantis.plugins.store import (
    StoreAccount,
    StoreAuthError,
    StoreError,
    StorePlugin,
    fetch_store,
    is_newer,
)

logger = logging.getLogger(__name__)


class _InstalledVersions(Protocol):
    def installed_version(self, plugin_id: str) -> str | None: ...


class PluginUpdates(QObject):
    # Не «changed»: подписки на .changed в src запрещены тестом настроек.
    updates_changed = Signal()

    def __init__(self, account: StoreAccount, registry: _InstalledVersions) -> None:
        super().__init__()
        self._account = account
        self._registry = registry
        self.store: list[StorePlugin] = []
        self.updates: dict[str, StorePlugin] = {}
        self.error = ""
        self.logged_out = False

    async def refresh(self) -> None:
        try:
            store = await fetch_store(self._account)
        except StoreAuthError:
            self.store = []
            self.updates = {}
            self.error = ""
            self.logged_out = True
        except StoreError as exc:
            # Прежний список не стираем: сеть моргнула — магазин не опустел.
            self.error = str(exc)
            logger.info("Магазин плагинов: %s", exc)
        else:
            self.store = store
            self.error = ""
            self.logged_out = False
            self.updates = self._count()
        self.updates_changed.emit()

    def recount(self) -> None:
        """Пересчитать обновления по уже загруженному магазину."""
        self.updates = self._count()
        self.updates_changed.emit()

    def _count(self) -> dict[str, StorePlugin]:
        found: dict[str, StorePlugin] = {}
        for item in self.store:
            installed = self._registry.installed_version(item.plugin_id)
            if installed is not None and is_newer(item.version, installed):
                found[item.plugin_id] = item
        return found
