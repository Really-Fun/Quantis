import sys
import os
import asyncio
import logging

# В exe requests может не найти CA-бандл — без него запрос за visitor_id к YouTube падает, поиск 0 результатов
if getattr(sys, "frozen", False):
    try:
        import pkgutil
        cert_data = pkgutil.get_data("certifi", "cacert.pem")
        if cert_data:
            import tempfile
            fd, path = tempfile.mkstemp(suffix=".pem")
            os.close(fd)
            with open(path, "wb") as f:
                f.write(cert_data)
            os.environ["REQUESTS_CA_BUNDLE"] = path
            os.environ["SSL_CERT_FILE"] = path
    except Exception:
        pass

from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from services import TrackHistoryService
from ui import NeonMusic


def _setup_logging() -> None:
    """Мини-логи для отладки (поиск, YTMusic). В exe — ещё и в файл."""
    fmt = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s", datefmt="%H:%M:%S")
    root = logging.getLogger("cleanplayer")
    root.setLevel(logging.INFO)
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(fmt)
        root.addHandler(h)
    if getattr(sys, "frozen", False):
        try:
            base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
            log_dir = os.path.dirname(sys.executable)
            log_path = os.path.join(log_dir, "cleanplayer.log")
            fh = logging.FileHandler(log_path, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)
            root.info("Лог exe: %s", log_path)
        except Exception:
            pass


if __name__ == "__main__":
    _setup_logging()
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