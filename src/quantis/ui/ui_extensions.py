"""UI-слоты расширений: nav + player bar + страницы (для плагинов и ядра)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget


@dataclass
class NavExtension:
    item_id: str
    tooltip: str
    icon: QIcon | None
    page_id: int
    from_plugin: bool = False
    on_click: Callable[[], None] | None = None


@dataclass
class PlayerActionExtension:
    action_id: str
    tooltip: str
    icon: QIcon | None
    callback: Callable[[], None]
    from_plugin: bool = False


@dataclass
class PageExtension:
    """Страница плагина в QStackedWidget MainWindow."""

    page_id: str
    title: str
    widget: QWidget
    subtitle: str = ""
    icon: QIcon | None = None
    stack_index: int | None = None
    from_plugin: bool = True


@dataclass
class BackgroundLayerExtension:
    """Слой между обоями и интерфейсом (визуализаторы, эффекты)."""

    layer_id: str
    widget: QWidget
    z_order: int = 0
    from_plugin: bool = True


class UiExtensionHost(QObject):
    """Регистрация пунктов sidebar, кнопок player bar, страниц и фоновых слоёв."""

    nav_changed = Signal()
    player_actions_changed = Signal()
    pages_changed = Signal()
    background_layers_changed = Signal()

    _instance: UiExtensionHost | None = None

    def __new__(cls) -> UiExtensionHost:
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._initialized = False
            cls._instance = obj
        return cls._instance

    def __init__(self) -> None:
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._nav: list[NavExtension] = []
        self._player_actions: list[PlayerActionExtension] = []
        self._pages: list[PageExtension] = []
        self._background_layers: list[BackgroundLayerExtension] = []
        self._initialized = True

    @classmethod
    def instance(cls) -> UiExtensionHost:
        return cls()

    def register_nav_item(self, item: NavExtension) -> None:
        self._nav = [n for n in self._nav if n.item_id != item.item_id]
        self._nav.append(item)
        self.nav_changed.emit()

    def unregister_nav_item(self, item_id: str) -> None:
        before = len(self._nav)
        self._nav = [n for n in self._nav if n.item_id != item_id]
        if len(self._nav) != before:
            self.nav_changed.emit()

    def register_player_action(self, action: PlayerActionExtension) -> None:
        self._player_actions = [
            a for a in self._player_actions if a.action_id != action.action_id
        ]
        self._player_actions.append(action)
        self.player_actions_changed.emit()

    def unregister_player_action(self, action_id: str) -> None:
        before = len(self._player_actions)
        self._player_actions = [
            a for a in self._player_actions if a.action_id != action_id
        ]
        if len(self._player_actions) != before:
            self.player_actions_changed.emit()

    def register_page(self, page: PageExtension) -> None:
        self._pages = [p for p in self._pages if p.page_id != page.page_id]
        self._pages.append(page)
        self.pages_changed.emit()

    def unregister_page(self, page_id: str) -> None:
        before = len(self._pages)
        self._pages = [p for p in self._pages if p.page_id != page_id]
        if len(self._pages) != before:
            self.pages_changed.emit()

    def register_background_layer(self, layer: BackgroundLayerExtension) -> None:
        self._background_layers = [
            item for item in self._background_layers if item.layer_id != layer.layer_id
        ]
        self._background_layers.append(layer)
        self._background_layers.sort(key=lambda item: item.z_order)
        self.background_layers_changed.emit()

    def unregister_background_layer(self, layer_id: str) -> None:
        before = len(self._background_layers)
        self._background_layers = [
            item for item in self._background_layers if item.layer_id != layer_id
        ]
        if len(self._background_layers) != before:
            self.background_layers_changed.emit()

    def background_layers(self) -> list[BackgroundLayerExtension]:
        return list(self._background_layers)

    def nav_items(self) -> list[NavExtension]:
        return list(self._nav)

    def player_actions(self) -> list[PlayerActionExtension]:
        return list(self._player_actions)

    def pages(self) -> list[PageExtension]:
        return list(self._pages)

    def get_page(self, page_id: str) -> PageExtension | None:
        return next((p for p in self._pages if p.page_id == page_id), None)

    def clear(self) -> None:
        self._nav.clear()
        self._player_actions.clear()
        self._pages.clear()
        self._background_layers.clear()
        self.nav_changed.emit()
        self.player_actions_changed.emit()
        self.pages_changed.emit()
        self.background_layers_changed.emit()
