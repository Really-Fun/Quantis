import sys
import os
import asyncio
import logging

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from player import Player
from services import TrackHistoryService
from ui import Quantis
from adapter import CleanAdapter


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
            # logging.FileHandler("app.log") 
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info("""
    --------------
    Quantis v0.1.1
    --------------""")

    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    player = Player()
    CleanAdapter(player, loop)

    window = Quantis()
    window.show()

    with loop:
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(TrackHistoryService().close())