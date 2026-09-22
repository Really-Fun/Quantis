"""Базовый класс для всех плагинов Quantis."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QSettings

from quantis.core.plugin_host import PluginHost


class BasePlugin:
    """Базовый класс для всех плагинов Quantis."""

    name: str = "Без названия"
    version: str = "0.0.0"
    author: str = "Unknown"
    description: str = ""
    icon: str = ""

    def __init__(self, host: PluginHost, settings: QSettings | None = None) -> None:
        self.host = host
        self.settings = settings
        self._async_wrappers: dict[Callable[..., Any], Callable[..., Any]] = {}

    @property
    def app(self) -> PluginHost:
        """Алиас для обратной совместимости с примерами в документации."""
        return self.host

    async def on_load(self) -> None:
        ...

    async def on_unload(self) -> None:
        ...

    async def on_minimize(self) -> None:
        ...

    async def on_restore(self) -> None:
        ...

    def subscribe(self, event: str, callback: Callable[..., Any]) -> None:
        """Подписка на событие. async-колбэки автоматически планируются в фоне."""
        wrapped = self._wrap_callback(callback)
        self.host.event_bus.subscribe(event, wrapped)

    def unsubscribe(self, event: str, callback: Callable[..., Any]) -> None:
        wrapped = self._async_wrappers.pop(callback, callback)
        self.host.event_bus.unsubscribe(event, wrapped)

    def _wrap_callback(self, callback: Callable[..., Any]) -> Callable[..., Any]:
        if not inspect.iscoroutinefunction(callback):
            return callback
        if callback in self._async_wrappers:
            return self._async_wrappers[callback]

        bridge = self.host.async_bridge

        def wrapper(*args: Any, **kwargs: Any) -> None:
            coro = callback(*args, **kwargs)
            if bridge is not None:
                bridge.schedule(coro)
            else:
                import logging

                logging.getLogger(__name__).warning(
                    "async-колбэк %s без AsyncBridge — coroutine не запущена",
                    callback.__qualname__,
                )
                coro.close()

        self._async_wrappers[callback] = wrapper
        return wrapper

    def __repr__(self) -> str:
        return f"<Plugin {self.name!r} v{self.version}>"

    __str__ = __repr__
