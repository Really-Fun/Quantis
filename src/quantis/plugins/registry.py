"""Реестр плагинов — центральное хранилище состояния сессии.

Управляет жизненным циклом плагинов: обнаружение → загрузка → включение → выключение.
Персистирует список включённых плагинов через QSettings.

Использование::

    registry = PluginRegistry.instance()
    await registry.load_all(context)           # при старте приложения
    await registry.enable("my_plugin")         # пользователь нажал "Включить"
    await registry.disable("my_plugin")        # пользователь нажал "Выключить"
    infos = registry.get_all()                 # для отображения в UI
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from PySide6.QtCore import QObject, QSettings, Signal

from quantis.plugins.loader import PluginLoader, PluginMeta

logger = logging.getLogger(__name__)

_SETTINGS_GROUP = "plugins/enabled"


@dataclass
class PluginInfo:
    """Полное состояние плагина для отображения в UI."""

    meta: PluginMeta
    is_active: bool = False
    error: str = ""


class PluginRegistry(QObject):
    """Singleton-реестр плагинов.

    Эмитит ``plugin_changed(plugin_id)`` при любом изменении состояния плагина.
    """

    plugin_changed = Signal(str)  # plugin_id

    _instance: PluginRegistry | None = None

    # ── Singleton ────────────────────────────────────────────────────────────

    @classmethod
    def instance(cls) -> PluginRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        self._loader = PluginLoader()
        self._settings = QSettings("ReallyFun", "Quantis")
        self._infos: dict[str, PluginInfo] = {}
        self._active: dict[str, object] = {}  # plugin_id → BasePlugin instance
        self._host = None  # PluginHost, задаётся в load_all

    # ── Публичный API ─────────────────────────────────────────────────────────

    async def load_all(self, host) -> None:
        """Сканирует папку плагинов и загружает включённые.

        Вызывать один раз при старте приложения.
        """
        self._host = host
        enabled_ids = self._read_enabled()

        for meta in self._loader.discover():
            info = PluginInfo(meta=meta)
            self._infos[meta.plugin_id] = info
            if not meta.is_valid:
                info.error = "; ".join(meta.errors)
                continue
            if meta.plugin_id in enabled_ids:
                await self._do_enable(meta.plugin_id)

        logger.info(
            "Найдено плагинов: %s, включено: %s", len(self._infos), len(self._active)
        )

    async def enable(self, plugin_id: str) -> bool:
        """Включает плагин: загружает, вызывает ``on_load()``, сохраняет в настройки.

        Returns:
            ``True`` при успехе, ``False`` при ошибке.
        """
        if plugin_id in self._active:
            return True
        success = await self._do_enable(plugin_id)
        if success:
            self._save_enabled()
        return success

    async def disable(self, plugin_id: str) -> None:
        """Выключает плагин: вызывает ``on_unload()``, удаляет из памяти."""
        instance = self._active.pop(plugin_id, None)
        if instance is not None:
            try:
                await instance.on_unload()
            except Exception:
                logger.exception("Ошибка в on_unload() плагина '%s'", plugin_id)

        if plugin_id in self._infos:
            self._infos[plugin_id].is_active = False
            self._infos[plugin_id].error = ""

        self._save_enabled()
        self.plugin_changed.emit(plugin_id)
        logger.info("Плагин '%s' выключен", plugin_id)

    def get_all(self) -> list[PluginInfo]:
        """Возвращает список всех найденных плагинов с их статусом."""
        return list(self._infos.values())

    def get_info(self, plugin_id: str) -> PluginInfo | None:
        return self._infos.get(plugin_id)

    def is_active(self, plugin_id: str) -> bool:
        return plugin_id in self._active

    async def unload_all(self) -> None:
        """Выключает все активные плагины при завершении (настройки не трогаем)."""
        for plugin_id in list(self._active):
            instance = self._active.pop(plugin_id, None)
            if instance is not None:
                try:
                    await instance.on_unload()
                except Exception:
                    logger.exception("Ошибка в on_unload() плагина '%s'", plugin_id)
            if plugin_id in self._infos:
                self._infos[plugin_id].is_active = False
        logger.info("Все плагины выгружены")

    def rescan(self) -> None:
        """Повторно сканирует папку плагинов (новые без перезапуска)."""
        for meta in self._loader.discover():
            if meta.plugin_id in self._infos:
                continue
            info = PluginInfo(meta=meta)
            if not meta.is_valid:
                info.error = "; ".join(meta.errors)
            self._infos[meta.plugin_id] = info
            self.plugin_changed.emit(meta.plugin_id)

    # ── Внутренние методы ─────────────────────────────────────────────────────

    async def _do_enable(self, plugin_id: str) -> bool:
        """Загружает и запускает плагин. Возвращает True при успехе."""
        info = self._infos.get(plugin_id)
        if info is None:
            logger.error("Плагин '%s' не найден в реестре", plugin_id)
            return False

        try:
            plugin_class = self._loader.load_class(info.meta)
            plugin_settings = QSettings("ReallyFun", f"Quantis/plugins/{plugin_id}")
            instance = plugin_class(self._host, plugin_settings)

            await instance.on_load()
            self._active[plugin_id] = instance
            info.is_active = True
            info.error = ""
            self.plugin_changed.emit(plugin_id)
            logger.info("Плагин '%s' v%s включён", plugin_id, info.meta.version)
            return True

        except Exception as e:
            info.is_active = False
            info.error = str(e)
            logger.exception("Ошибка при включении плагина '%s'", plugin_id)
            self.plugin_changed.emit(plugin_id)
            return False

    def _read_enabled(self) -> set[str]:
        """Читает список включённых плагинов из QSettings."""
        raw = self._settings.value(_SETTINGS_GROUP, [])
        # Пустой QStringList Qt отдаёт как None — иначе падает загрузка всех плагинов.
        if raw is None:
            return set()
        if isinstance(raw, str):
            return {raw} if raw else set()
        return set(raw)

    def _save_enabled(self) -> None:
        """Сохраняет список включённых плагинов в QSettings."""
        self._settings.setValue(_SETTINGS_GROUP, list(self._active.keys()))
