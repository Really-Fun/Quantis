import logging
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from quantis.core.async_bridge import AsyncBridge
from quantis.core.bootstrap import build_application, shutdown_application
from quantis.ui import Quantis
from quantis.version import __version__


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger(__name__)
    logger.info(
        """
    --------------
    Quantis v%s
    --------------
        """,
        __version__,
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Quantis")
    app.setApplicationDisplayName("Quantis")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("ReallyFun")
    # Wayland берёт app_id отсюда, иначе окно опознаётся как "python3".
    app.setDesktopFileName("quantis")
    bridge = AsyncBridge()
    bridge.setParent(app)
    bundle = build_application(bridge)

    # Сначала окно и первый кадр — плагины/адаптер после show.
    window = Quantis(bundle)
    window.show()

    def _post_show() -> None:
        from quantis.plugins import PluginRegistry

        bridge.schedule(PluginRegistry.instance().load_all(bundle.plugin_host))
        if os.environ.get("QUANTIS_ENABLE_ADAPTER", "1").lower() in (
            "1",
            "true",
            "yes",
        ):
            try:
                from quantis.adapter import CleanAdapter

                CleanAdapter(
                    player=bundle.player,
                    event_bus=bundle.event_bus,
                    path_provider=bundle.music.provider,
                    bridge=bridge,
                )
            except Exception:
                logger.exception("Системная интеграция плеера недоступна")

    QTimer.singleShot(0, _post_show)

    try:
        sys.exit(app.exec())
    finally:
        shutdown_application(bundle)
        bridge.shutdown()


if __name__ == "__main__":
    main()
