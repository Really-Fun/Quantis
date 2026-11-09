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

import asyncio
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal

from quantis.plugins.installer import (
    PluginInstallError,
    drop_backup,
    install_plugin_from_zip,
    restore_backup,
)
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

    def __init__(
        self,
        loader: PluginLoader | None = None,
        settings: QSettings | None = None,
    ) -> None:
        super().__init__()
        self._loader = loader or PluginLoader()
        self._settings = settings or QSettings("ReallyFun", "Quantis")
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

    # ── Установка из магазина ────────────────────────────────────────────────

    def installed_version(self, plugin_id: str) -> str | None:
        info = self._infos.get(plugin_id)
        return info.meta.version if info is not None else None

    def is_bundled(self, plugin_id: str) -> bool:
        """Плагин из комплекта программы (не из пользовательской папки)."""
        info = self._infos.get(plugin_id)
        if info is None:
            return False
        try:
            return not info.meta.path.resolve().is_relative_to(
                self._loader.user_dir.resolve()
            )
        except (OSError, ValueError):
            return True

    async def install(self, zip_path: Path, plugin_id: str) -> bool:
        """Ставит или обновляет плагин без перезапуска.

        Новый плагин включается сразу; обновлённый — если был включён. Если
        новая версия не запустилась, возвращаем прежние файлы и включаем
        старую версию; результат — False. PluginInstallError (битый архив,
        чужой id) пробрасывается, ничего не тронув.
        """
        user_dir = self._loader.user_dir
        previous = self._infos.get(plugin_id)
        was_active = plugin_id in self._active
        is_new = previous is None or self.is_bundled(plugin_id)

        # Работающий плагин гасим до замены файлов; битый архив или чужой id
        # ничего не заменяют — тогда включаем его обратно.
        target = user_dir / plugin_id
        if was_active:
            await self.disable(plugin_id)
        try:
            await asyncio.to_thread(
                install_plugin_from_zip,
                zip_path,
                plugin_id=plugin_id,
                plugins_dir=user_dir,
                keep_backup=True,
            )
        except PluginInstallError:
            if was_active:
                await self.enable(plugin_id)
            raise

        self._loader.forget_modules(plugin_id, target)
        if previous is not None:
            self._loader.forget_modules(plugin_id, previous.meta.path)
        self._register_meta(self._loader.read_meta(target))

        if not (is_new or was_active):
            await asyncio.to_thread(drop_backup, plugin_id, user_dir)
            return True
        if await self.enable(plugin_id):
            await asyncio.to_thread(drop_backup, plugin_id, user_dir)
            return True

        error = self._infos[plugin_id].error
        logger.warning(
            "Плагин '%s' не запустился после установки: %s", plugin_id, error
        )
        restored = await asyncio.to_thread(restore_backup, plugin_id, user_dir)
        self._loader.forget_modules(plugin_id, target)
        if restored:
            self._register_meta(self._loader.read_meta(target))
            if was_active:
                await self.enable(plugin_id)
            self._infos[plugin_id].error = error
            self.plugin_changed.emit(plugin_id)
        return False

    async def uninstall(self, plugin_id: str) -> None:
        info = self._infos.get(plugin_id)
        if info is None:
            return
        if self.is_bundled(plugin_id):
            raise PluginInstallError("Встроенный плагин удалить нельзя")
        await self.disable(plugin_id)
        path = info.meta.path
        self._loader.forget_modules(plugin_id, path)
        await asyncio.to_thread(shutil.rmtree, path, True)
        self._infos.pop(plugin_id, None)
        # Под ним мог лежать одноимённый плагин из комплекта — показываем его.
        self.rescan()
        self.plugin_changed.emit(plugin_id)
        logger.info("Плагин '%s' удалён", plugin_id)

    def _register_meta(self, meta: PluginMeta) -> None:
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
