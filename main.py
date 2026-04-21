import sys
import os
import asyncio

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from player import Player
from services import TrackHistoryService
from ui import NeonMusic
from adapter import CleanAdapter


if __name__ == "__main__":
    app = QApplication(sys.argv)
    if os.path.exists("user_theme.xml"):
        apply_stylesheet(app, "user_theme.xml", invert_secondary=True)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    player = Player()
    CleanAdapter(player)

    window = NeonMusic()
    window.show()

    with loop:
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(TrackHistoryService().close())