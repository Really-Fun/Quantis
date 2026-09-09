"""Оркестрация: скрипт → TTS → duck + overlay → fade-up."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation

from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track
from quantis.player import Player

from config import SpeakerConfig
from overlay import VoiceOverlay
from script import build_script, is_radio_playlist
from tts import cache_file, synthesize
from wikipedia import WikipediaFacts

FADE_MS = 1500


class Announcer(QObject):
    """Живёт в UI-потоке. Генерация речи — в фоне через AsyncBridge."""

    def __init__(
        self,
        player: Player,
        overlay: VoiceOverlay,
        bridge: AsyncBridge,
        cache_dir: Path,
        *,
        playlist_of: Callable[[], object | None],
        parent: QObject | None = None,
        facts: WikipediaFacts | None = None,
        synth: Callable[..., Awaitable[Path | None]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._player = player
        self._overlay = overlay
        self._bridge = bridge
        self._cache_dir = cache_dir
        self._playlist_of = playlist_of
        self._facts = facts or WikipediaFacts()
        self._synth = synth or synthesize
        self._config = SpeakerConfig()
        self._seq = 0
        self._fade: QVariantAnimation | None = None
        self._unloaded = False

        self._overlay.ended.connect(self._on_overlay_ended)

    def set_config(self, config: SpeakerConfig) -> None:
        self._config = config
        if not config.enabled:
            self.cancel(restore=True)

    def cancel(self, *, restore: bool = True) -> None:
        self._seq += 1
        self._overlay.stop()
        self._stop_fade()
        if restore:
            self._player.set_duck_gain(1.0)

    def shutdown(self) -> None:
        self._unloaded = True
        self.cancel(restore=True)

    def pause_voice(self) -> None:
        self._overlay.pause()

    def resume_voice(self) -> None:
        self._overlay.resume()

    async def handle_track(self, track: Track) -> None:
        self._seq += 1
        seq = self._seq

        def reset() -> None:
            if seq != self._seq:
                return
            self._reset_output()

        await self._bridge.call_main(reset)

        if self._unloaded or not self._config.enabled:
            return
        if not is_radio_playlist(self._playlist_of()):
            return

        fact = await self._facts.fact_for(track.author)
        if seq != self._seq or self._unloaded:
            return
        script = build_script(track.title, track.author, fact)
        dest = cache_file(
            self._cache_dir, self._config.voice, self._config.rate, script
        )
        path = await self._synth(
            script,
            dest,
            voice=self._config.voice,
            rate=self._config.rate,
        )
        if seq != self._seq or self._unloaded or path is None:
            return

        def start() -> None:
            if seq != self._seq or self._unloaded:
                return
            self._stop_fade()
            self._player.set_duck_gain(self._config.duck_gain)
            self._overlay.play(path)

        await self._bridge.call_main(start)

    async def preview(self) -> bool:
        script = build_script("Breathe", "The Prodigy", FALLBACK_PREVIEW_FACT)
        dest = cache_file(
            self._cache_dir, self._config.voice, self._config.rate, script
        )
        path = await self._synth(
            script,
            dest,
            voice=self._config.voice,
            rate=self._config.rate,
        )
        if path is None or self._unloaded:
            return False

        def start() -> None:
            if self._unloaded:
                return
            self._overlay.stop()
            self._overlay.play(path)

        await self._bridge.call_main(start)
        return True

    def _reset_output(self) -> None:
        self._overlay.stop()
        self._stop_fade()
        self._player.set_duck_gain(1.0)

    def _on_overlay_ended(self) -> None:
        if self._unloaded:
            return
        self._fade_to(1.0)

    def _stop_fade(self) -> None:
        fade = self._fade
        self._fade = None
        if fade is not None:
            fade.stop()
            fade.deleteLater()

    def _fade_to(self, target: float) -> None:
        self._stop_fade()
        start = self._player.duck_gain()
        if abs(start - target) < 0.01:
            self._player.set_duck_gain(target)
            return
        fade = QVariantAnimation(self)
        fade.setStartValue(float(start))
        fade.setEndValue(float(target))
        fade.setDuration(FADE_MS)
        fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        fade.valueChanged.connect(
            lambda value: self._player.set_duck_gain(float(value))
        )
        fade.finished.connect(self._stop_fade)
        self._fade = fade
        fade.start()


FALLBACK_PREVIEW_FACT = "The Prodigy записали The Fat of the Land в 1997 году."
