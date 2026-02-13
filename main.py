import sys
import asyncio

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from services import TrackHistoryService
from ui import NeonMusic


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_stylesheet(app, "user_theme.xml", invert_secondary=True)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = NeonMusic()
    window.show()

    with loop:
        try:
            loop.run_forever()
        finally:
            # Закрываем соединение с SQLite, чтобы процесс завершался корректно.
            loop.run_until_complete(TrackHistoryService().close())