import sys
import os
import asyncio
import platform

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from player import Player
from services import TrackHistoryService
from ui import NeonMusic


if __name__ == "__main__":
    app = QApplication(sys.argv)
    if os.path.exists("user_theme.xml"):
        apply_stylesheet(app, "user_theme.xml", invert_secondary=False)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    player = Player()

    current_os = platform.system()

    if current_os == "Linux":
        from mpris_server.server import Server
        from player.MprisAdapter import NeonAppAdapter, NeonEventHandler
        mpris_adapter = NeonAppAdapter(player)
        mpris = Server("NeonApp", mpris_adapter)
        event_handler = NeonEventHandler(mpris.root, mpris.player)
        mpris_adapter.set_event_handler(event_handler)
        mpris.publish()

    elif current_os == "Windows":
        from player.windows_adapter import WindowsSMTCAdapter 
        windows_adapter = WindowsSMTCAdapter(player, loop)
        # windows_adapter.publish()

    window = NeonMusic()
    window.show()

    with loop:
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(TrackHistoryService().close())