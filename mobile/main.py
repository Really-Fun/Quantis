"""Quantis Mobile — бета для Android: Яндекс Музыка и YouTube.

Интерфейс — Qt Quick (QML, стиль Material) в qml/, логика — backend.py.
Оба источника играют сразу: Яндекс — по прямой ссылке, YouTube — через
локальный прокси (stream_proxy.py), который добавляет нужные заголовки.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# На телефоне FFmpeg-бэкенд Qt открывал поток AAudio, тот сразу отключался
# («stream disconnected»), и так по кругу: трек «играл» без звука. Системный
# MediaPlayer Android играет и файлы, и ссылки сам. Задать до QtMultimedia.
if hasattr(sys, "getandroidapilevel"):
    os.environ.setdefault("QT_MEDIA_BACKEND", "android")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Material")

from PySide6.QtCore import QStandardPaths, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402

HERE = Path(__file__).resolve().parent


def _install_ca_bundle() -> None:
    """У Python на Android нет системных сертификатов для OpenSSL.

    Без них любой HTTPS-запрос падает на проверке. Сборка кладёт
    сертификаты в модуль ca_bundle.py (файлы .pem в APK не попадают).
    """
    try:
        from ca_bundle import PEM
    except ImportError:  # на компьютере сертификаты есть и без него
        return
    target = (
        Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.CacheLocation
            )
            or Path.home()
        )
        / "cacert.pem"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists() or target.read_text(encoding="ascii") != PEM:
        target.write_text(PEM, encoding="ascii")
    os.environ["SSL_CERT_FILE"] = str(target)
    os.environ["QUANTIS_CA_FILE"] = str(target)  # для certifi.py рядом


def main() -> None:
    app = QGuiApplication(sys.argv)
    app.setApplicationName("QuantisMobile")
    app.setOrganizationName("ReallyFun")
    _install_ca_bundle()  # после приложения: нужен путь к кэшу

    from art import ArtProvider
    from backend import AppController

    controller = AppController()
    engine = QQmlApplicationEngine()
    engine.addImageProvider("art", ArtProvider())
    engine.rootContext().setContextProperty("app", controller)
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        sys.exit("Не удалось загрузить интерфейс (qml/Main.qml)")
    app.aboutToQuit.connect(controller.shutdown)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
