'''Определяет и подключает подходящий к операционной системе Remote Control API (Media Control API)
Linux - MPRIS
Windows - SMTC
'''
from asyncio import AbstractEventLoop
import platform
import importlib.util

from player import Player

class CleanAdapter:
    """Создаём нужный адаптер в зависимости от ОС пользователя"""

    def __init__(self, player: Player, loop: AbstractEventLoop) -> CleanAdapter:
        current_os = platform.system()

        match current_os:
            case "Linux":
                self.start_mpris(player=player)

            case "Windows":
                self.start_smtc(player=player, loop=loop)

    def start_mpris(self, player: Player) -> None:
        """Запускаем MPRIS для линукс

        Args:
            player (_type_): Сам vlc проигрыватель
        """
        from mpris_server.server import Server
        from .MprisAdapter import QuantisAppAdapter, QuantisEventHandler

        mpris_adapter = QuantisAppAdapter(player)
        mpris = Server("Quantis", mpris_adapter)
        event_handler = QuantisEventHandler(mpris.root, mpris.player)
        mpris_adapter.set_event_handler(event_handler)
        mpris.publish()

    def start_smtc(self, player: Player, loop: AbstractEventLoop) -> None:
        """Запускаем SMTC для Windows

        Args:
            player (Player): Сам vlc проигрыватель
            loop (_type_): Текущий событийный цикл
        """
        from .windows_adapter import WindowsSMTCAdapter

        windows_adapter = WindowsSMTCAdapter(player, loop)