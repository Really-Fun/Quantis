import sys
import os
import asyncio

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet
from mpris_server.server import Server

from player import Player, NeonAppAdapter, NeonEventHandler
from services import TrackHistoryService
from ui import NeonMusic


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_stylesheet(app, "user_theme.xml", invert_secondary=True)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    player = Player()
    mpris = Server("NeonApp", NeonAppAdapter(player))
    event_handler = NeonEventHandler(mpris.root, mpris.player)
    window = NeonMusic()
    window.show()

    with loop:
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(TrackHistoryService().close())