"""Определяет и подключает подходящий к операционной системе Remote Control API (Media Control API)
Linux - MPRIS
Windows - SMTC
"""

from __future__ import annotations

import logging
import platform

from quantis.core.async_bridge import AsyncBridge
from quantis.player.player import Player
from quantis.plugins.event_bus import EventBus
from quantis.providers.path_provider import PathProvider


class CleanAdapter:
    """Создаём нужный адаптер в зависимости от ОС пользователя."""

    def __init__(
        self,
        *,
        player: Player,
        event_bus: EventBus,
        path_provider: PathProvider,
        bridge: AsyncBridge,
    ) -> None:
        current_os = platform.system()

        match current_os:
            case "Linux":
                self.start_mpris(
                    player=player,
                    event_bus=event_bus,
                    path_provider=path_provider,
                )
            case "Windows":
                self.start_smtc(player=player, bridge=bridge, event_bus=event_bus)

    def start_mpris(self, player: Player, event_bus, path_provider) -> None:
        from mpris_server.server import Server

        from .mpris_adapter import QuantisAppAdapter, QuantisEventHandler

        mpris_adapter = QuantisAppAdapter(player, event_bus, path_provider)
        mpris = Server("Quantis", mpris_adapter)
        event_handler = QuantisEventHandler(mpris.root, mpris.player)
        mpris_adapter.set_event_handler(event_handler)
        mpris.publish()

    def start_smtc(self, player: Player, bridge: AsyncBridge, event_bus) -> None:
        try:
            from .windows_adapter import WindowsSMTCAdapter

            WindowsSMTCAdapter(player, bridge, event_bus)
        except Exception:
            logging.getLogger(__name__).exception(
                "Windows SMTC недоступен — управление из системного оверлея отключено"
            )
