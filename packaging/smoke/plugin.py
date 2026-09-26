"""Плагин-проверка собранного Quantis: исполняется Python-ом самого exe.

Запускают packaging/scripts/smoke_bundle.ps1 (Windows) и smoke_bundle.sh
(Linux): звук mp3/m4a/webm через FFmpeg Qt Multimedia, SVG-иконки, темы,
стили, импорты, экстракторы yt-dlp, сертификаты. Итог — JSON в SMOKE_OUT.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

from quantis.plugins.base import BasePlugin


class BundleSmoke(BasePlugin):
    name = "smoke"

    async def on_load(self) -> None:
        await self.host.async_bridge.call_main(self._start)

    def _start(self) -> None:
        from PySide6.QtCore import QSize, QTimer, QUrl
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        out: dict = {"imports": {}, "audio": {}}
        for mod in (
            "yt_dlp",
            "ytmusicapi",
            "yandex_music",
            "keyring",
            "aiohttp",
            "certifi",
        ):
            try:
                importlib.import_module(mod)
                out["imports"][mod] = "ok"
            except Exception as exc:  # noqa: BLE001
                out["imports"][mod] = f"{type(exc).__name__}: {exc}"
        import certifi
        from yt_dlp.extractor import gen_extractor_classes

        extractors = list(gen_extractor_classes())
        out["yt_dlp_extractors"] = len(extractors)
        out["yt_dlp_youtube"] = any(e.IE_NAME == "youtube" for e in extractors)
        out["certifi_pem"] = Path(certifi.where()).is_file()
        from quantis.ui import resources
        from quantis.ui.themes import registry

        out["themes"] = sorted(t.id for t in registry.all())
        icon = resources.load_icon("heart.svg")
        out["svg_icon"] = not icon.pixmap(QSize(32, 32)).isNull()
        out["qss_len"] = len(resources.load_stylesheet(out["themes"][0]))

        files = sorted(Path(os.environ["SMOKE_MEDIA"]).glob("sample.*"))
        self._player = QMediaPlayer()
        self._audio = QAudioOutput()
        self._audio.setVolume(0.0)
        self._player.setAudioOutput(self._audio)

        def play_next() -> None:
            if not files:
                Path(os.environ["SMOKE_OUT"]).write_text(
                    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                os._exit(0)
            path = files.pop(0)
            self._player.setSource(QUrl.fromLocalFile(str(path)))
            self._player.play()

            def check() -> None:
                out["audio"][path.suffix] = {
                    "position_ms": self._player.position(),
                    "duration_ms": self._player.duration(),
                    "error": self._player.errorString() or None,
                }
                self._player.stop()
                play_next()

            QTimer.singleShot(2500, check)

        QTimer.singleShot(500, play_next)
