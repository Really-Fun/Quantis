'''Определяет и подключает подходящий к операционной системе плеер-адаптер'''
import platform

from player import Player

class CleanAdapter:

    def __init__(self, player: Player, loop) -> CleanAdapter:
        current_os = platform.system()

        if current_os == "Linux":
            from mpris_server.server import Server
            from .MprisAdapter import NeonAppAdapter, NeonEventHandler

            mpris_adapter = NeonAppAdapter(player)
            mpris = Server("NeonApp", mpris_adapter)
            event_handler = NeonEventHandler(mpris.root, mpris.player)
            mpris_adapter.set_event_handler(event_handler)
            mpris.publish()

        elif current_os == "Windows":
            from .windows_adapter import WindowsSMTCAdapter

            windows_adapter = WindowsSMTCAdapter(player, loop)