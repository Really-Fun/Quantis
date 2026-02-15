import sys
import os
import asyncio

# В exe: путь к локалям ytmusicapi и CA-бандл для requests
if getattr(sys, "frozen", False):
    _meipass = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    # Чтобы ytmusicapi нашёл locales (в т.ч. ru), подменяем __file__ модуля ytmusic
    try:
        import ytmusicapi.ytmusic as _ytm_mod
        _ytm_mod.__file__ = os.path.join(_meipass, "ytmusicapi", "ytmusic.py")
    except Exception:
        pass
    # Запрос за X-Goog-Visitor-Id к music.youtube.com часто получает пустую страницу при старом UA.
    # Подменяем User-Agent на актуальный Chrome, чтобы сервер отдал страницу с ytcfg (VISITOR_DATA).
    try:
        import ytmusicapi.helpers as _ytm_helpers
        _orig_init_headers = _ytm_helpers.initialize_headers
        _chrome_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        def _patched_init_headers():
            h = _orig_init_headers()
            h["user-agent"] = _chrome_ua
            return h
        _ytm_helpers.initialize_headers = _patched_init_headers
    except Exception:
        pass
    _cert_paths = (
        os.path.join(_meipass, "certifi", "cacert.pem"),
        os.path.join(_meipass, "certifi", "certifi", "cacert.pem"),
    )
    _ca_bundle_set = False
    for _p in _cert_paths:
        if os.path.isfile(_p):
            os.environ["REQUESTS_CA_BUNDLE"] = _p
            os.environ["SSL_CERT_FILE"] = _p
            _ca_bundle_set = _p
            break
    if not _ca_bundle_set:
        try:
            import pkgutil
            import tempfile
            _cert_data = pkgutil.get_data("certifi", "cacert.pem")
            if _cert_data:
                _fd, _p = tempfile.mkstemp(suffix=".pem")
                os.close(_fd)
                with open(_p, "wb") as _f:
                    _f.write(_cert_data)
                os.environ["REQUESTS_CA_BUNDLE"] = _p
                os.environ["SSL_CERT_FILE"] = _p
                _ca_bundle_set = _p
        except Exception:
            pass
from qasync import QEventLoop
from PySide6.QtWidgets import QApplication
from qt_material import apply_stylesheet

from services import TrackHistoryService
from ui import NeonMusic


if __name__ == "__main__":
    # onefile: сразу ставим рабочую папку в _MEIPASS, чтобы assets/icons и user_theme.xml находились
    if getattr(sys, "frozen", False):
        os.chdir(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    if getattr(sys, "frozen", False) and not os.environ.get("REQUESTS_CA_BUNDLE"):
        try:
            import certifi
            _p = certifi.where()
            if _p and os.path.isfile(_p):
                os.environ["REQUESTS_CA_BUNDLE"] = _p
                os.environ["SSL_CERT_FILE"] = _p
        except Exception:
            pass
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