import sys
import asyncio

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from ui import NeonMusic


async def main():
    main_app = QApplication(sys.argv)

    main_window = NeonMusic()
    main_window.show()

    main_loop = asyncio.get_running_loop()
    await main_loop.run_in_executor(None, main_app.exec)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = NeonMusic()
    window.show()

    with loop:
        loop.run_forever()