import sys
import asyncio

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from ui import NeonMusic


async def main():
    main_app = QApplication(sys.argv)

    main_window = NeonMusic()
    main_window.show()

    main_loop = asyncio.get_running_loop()
    await main_loop.run_in_executor(None, main_app.exec)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_stylesheet(app, "user_theme.xml", invert_secondary=True)

    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = NeonMusic()
    window.show()

    with loop:
        loop.run_forever()