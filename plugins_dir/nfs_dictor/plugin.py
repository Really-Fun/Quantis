"""NFS Speaker — диктор на волне и радио по треку."""

from __future__ import annotations

import logging
from pathlib import Path

from announcer import Announcer
from config import SpeakerConfig
from overlay import VoiceOverlay
from page import SpeakerPage
from PySide6.QtGui import QIcon
from tts import edge_tts_available

from quantis.plugins.base import BasePlugin
from quantis.utils import app_paths

logger = logging.getLogger(__name__)

PAGE_ID = "nfs_speaker"
PLUGIN_DIR = Path(__file__).resolve().parent


class NfsSpeaker(BasePlugin):
    """Факт + «а сейчас играет», трек приглушён через duck-gain."""

    name = "Need For Speed Speaker"
    version = "0.1.0"
    author = "Really-Fun"
    description = "Диктор сообщает, какой трек будет играть"
    icon = "nfs.png"

    async def on_load(self) -> None:
        self._page: SpeakerPage | None = None
        self._overlay: VoiceOverlay | None = None
        self._announcer: Announcer | None = None
        self._unloaded = False

        bridge = self.host.async_bridge
        if bridge is None:
            raise RuntimeError("NFS Speaker требует AsyncBridge")

        config = SpeakerConfig.load(self.settings)
        cache_dir = app_paths.cache_dir() / "nfs_speaker"
        cache_dir.mkdir(parents=True, exist_ok=True)
        tts_ready = edge_tts_available()
        player = self.host.playback.player

        def build_ui() -> None:
            icon = _plugin_icon()
            overlay = VoiceOverlay()
            announcer = Announcer(
                player,
                overlay,
                bridge,
                cache_dir,
                playlist_of=lambda: self.host.playback.playlist_manager.current_playlist,
            )
            announcer.set_config(config)
            self._overlay = overlay
            self._announcer = announcer

            page = SpeakerPage(config, self.settings, tts_ready=tts_ready)
            page.config_changed.connect(self._on_config_changed)
            page.preview_requested.connect(self._on_preview)
            self._page = page
            self.host.register_page(
                PAGE_ID,
                "Диктор",
                page,
                subtitle="Радио-объявления на волне",
                icon=icon,
            )

        await bridge.call_main(build_ui)

        self.subscribe("track_changed", self._on_track_changed)
        self.subscribe("playback_paused", self._on_paused)
        self.subscribe("playback_resumed", self._on_resumed)
        self.subscribe("playback_stopped", self._on_stopped)
        self.subscribe("track_finished", self._on_stopped)
        logger.info("NFS Speaker загружен")

    async def on_unload(self) -> None:
        self._unloaded = True
        self.unsubscribe("track_changed", self._on_track_changed)
        self.unsubscribe("playback_paused", self._on_paused)
        self.unsubscribe("playback_resumed", self._on_resumed)
        self.unsubscribe("playback_stopped", self._on_stopped)
        self.unsubscribe("track_finished", self._on_stopped)

        bridge = self.host.async_bridge
        page = self._page
        overlay = self._overlay
        announcer = self._announcer

        def destroy_ui() -> None:
            if announcer is not None:
                announcer.shutdown()
            self.host.unregister_page(PAGE_ID)
            if overlay is not None:
                overlay.stop()
                overlay.deleteLater()
            if page is not None:
                page.deleteLater()
            self._announcer = None
            self._overlay = None
            self._page = None

        if bridge is not None:
            bridge.invoke_main(destroy_ui)
        else:
            destroy_ui()
        logger.info("NFS Speaker выгружен")

    def _on_config_changed(self, config: SpeakerConfig) -> None:
        if self._announcer is not None:
            self._announcer.set_config(config)

    def _on_preview(self) -> None:
        announcer = self._announcer
        bridge = self.host.async_bridge
        if announcer is None or bridge is None:
            return
        bridge.schedule(announcer.preview())

    async def _on_track_changed(self, track) -> None:
        if self._unloaded or self._announcer is None:
            return
        await self._announcer.handle_track(track)

    def _on_paused(self) -> None:
        if self._announcer is not None:
            self._announcer.pause_voice()

    def _on_resumed(self) -> None:
        if self._announcer is not None:
            self._announcer.resume_voice()

    def _on_stopped(self) -> None:
        if self._announcer is not None:
            self._announcer.cancel(restore=True)


def _plugin_icon() -> QIcon | None:
    png = PLUGIN_DIR / "nfs.png"
    if png.is_file():
        return QIcon(str(png))
    try:
        from quantis.ui import resources

        return resources.load_icon("radio.svg")
    except Exception:
        return None
