"""Узкий контракт для плагинов (без God Object)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

if TYPE_CHECKING:
    from quantis.controllers.playback_controller import PlaybackController
    from quantis.core.async_bridge import AsyncBridge
    from quantis.plugins.event_bus import EventBus
    from quantis.services.music_service import MusicService


@dataclass
class PluginHost:
    event_bus: EventBus
    playback: PlaybackController
    music: MusicService
    async_bridge: AsyncBridge | None = None

    def register_nav_item(
        self,
        item_id: str,
        tooltip: str,
        page_id: int,
        *,
        icon: QIcon | None = None,
        on_click: Callable[[], None] | None = None,
    ) -> None:
        from quantis.ui.ui_extensions import NavExtension, UiExtensionHost

        UiExtensionHost.instance().register_nav_item(
            NavExtension(
                item_id=item_id,
                tooltip=tooltip,
                icon=icon,
                page_id=page_id,
                from_plugin=True,
                on_click=on_click,
            )
        )

    def unregister_nav_item(self, item_id: str) -> None:
        from quantis.ui.ui_extensions import UiExtensionHost

        UiExtensionHost.instance().unregister_nav_item(item_id)

    def register_player_action(
        self,
        action_id: str,
        tooltip: str,
        callback: Callable[[], None],
        *,
        icon: QIcon | None = None,
    ) -> None:
        from quantis.ui.ui_extensions import PlayerActionExtension, UiExtensionHost

        UiExtensionHost.instance().register_player_action(
            PlayerActionExtension(
                action_id=action_id,
                tooltip=tooltip,
                icon=icon,
                callback=callback,
                from_plugin=True,
            )
        )

    def unregister_player_action(self, action_id: str) -> None:
        from quantis.ui.ui_extensions import UiExtensionHost

        UiExtensionHost.instance().unregister_player_action(action_id)

    def register_page(
        self,
        page_id: str,
        title: str,
        widget: QWidget,
        *,
        subtitle: str = "",
        icon: QIcon | None = None,
    ) -> None:
        """Регистрирует страницу плагина. Создавать widget нужно в UI-потоке."""
        from PySide6.QtCore import Qt, QThread
        from PySide6.QtWidgets import QApplication

        from quantis.ui.ui_extensions import PageExtension, UiExtensionHost

        def do_register() -> None:
            widget.setWindowFlags(Qt.WindowType.Widget)
            UiExtensionHost.instance().register_page(
                PageExtension(
                    page_id=page_id,
                    title=title,
                    widget=widget,
                    subtitle=subtitle,
                    icon=icon,
                    from_plugin=True,
                )
            )

        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            if self.async_bridge is None:
                raise RuntimeError(
                    "register_page из фонового потока требует async_bridge"
                )
            self.async_bridge.invoke_main(do_register)
            return
        do_register()

    def unregister_page(self, page_id: str) -> None:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication

        from quantis.ui.ui_extensions import UiExtensionHost

        def do_unregister() -> None:
            self.unregister_nav_item(page_id)
            UiExtensionHost.instance().unregister_page(page_id)

        app = QApplication.instance()
        if (
            app is not None
            and QThread.currentThread() != app.thread()
            and self.async_bridge is not None
        ):
            self.async_bridge.invoke_main(do_unregister)
            return
        do_unregister()

    def register_background_layer(
        self,
        layer_id: str,
        widget: QWidget,
        *,
        z_order: int = 0,
    ) -> None:
        """Слой между обоями и интерфейсом. Создавать widget нужно в UI-потоке."""
        from PySide6.QtCore import Qt, QThread
        from PySide6.QtWidgets import QApplication

        from quantis.ui.ui_extensions import BackgroundLayerExtension, UiExtensionHost

        def do_register() -> None:
            widget.setWindowFlags(Qt.WindowType.Widget)
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            UiExtensionHost.instance().register_background_layer(
                BackgroundLayerExtension(
                    layer_id=layer_id,
                    widget=widget,
                    z_order=z_order,
                    from_plugin=True,
                )
            )

        app = QApplication.instance()
        if app is not None and QThread.currentThread() != app.thread():
            if self.async_bridge is None:
                raise RuntimeError(
                    "register_background_layer из фонового потока требует async_bridge"
                )
            self.async_bridge.invoke_main(do_register)
            return
        do_register()

    def unregister_background_layer(self, layer_id: str) -> None:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication

        from quantis.ui.ui_extensions import UiExtensionHost

        def do_unregister() -> None:
            UiExtensionHost.instance().unregister_background_layer(layer_id)

        app = QApplication.instance()
        if (
            app is not None
            and QThread.currentThread() != app.thread()
            and self.async_bridge is not None
        ):
            self.async_bridge.invoke_main(do_unregister)
            return
        do_unregister()
