"""Пакет системы плагинов Quantis."""

from .base import BasePlugin
from .event_bus import EventBus
from .installer import (
    PluginInstallError,
    install_plugin_from_url,
    install_plugin_from_zip,
)
from .loader import PluginLoader, PluginMeta
from .registry import PluginInfo, PluginRegistry

__all__ = [
    "BasePlugin",
    "EventBus",
    "PluginInstallError",
    "PluginLoader",
    "PluginMeta",
    "PluginRegistry",
    "PluginInfo",
    "install_plugin_from_url",
    "install_plugin_from_zip",
]
