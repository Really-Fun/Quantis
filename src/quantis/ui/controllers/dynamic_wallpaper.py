"""Динамические обои: видео текущего трека, в том числе часовые миксы."""

from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic

from PySide6.QtCore import QObject, QTimer

from quantis.controllers.playback_controller import PlaybackController
from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track
from quantis.plugins.event_bus import EventBus
from quantis.providers import PathProvider
from quantis.services.music_service import MusicService
from quantis.services.wallpaper_policy import (
    WALLPAPER_SYNC_DRIFT_MS,
    WALLPAPER_SYNC_INTERVAL_MS,
    should_fetch_wallpaper_now,
    should_play_local_wallpaper,
    wallpaper_decode_max_side,
    wallpaper_next_drift_tolerance,
    wallpaper_positions_drifted,
    wallpaper_source_has_video,
    wallpaper_source_meets_quality,
    wallpaper_stream_conflicts,
    wallpaper_url_itag,
)
from quantis.ui.preferences import UiPreferences
from quantis.ui.views.widgets.wallpaper_backdrop import WallpaperBackdrop

logger = logging.getLogger(__name__)


def _track_key(track: Track) -> str:
    return f"{track.source}:{track.track_id}"


class DynamicWallpaperController(QObject):
    def __init__(
        self,
        backdrop: WallpaperBackdrop,
        music: MusicService,
        bridge: AsyncBridge,
        preferences: UiPreferences,
        event_bus: EventBus,
        playback: PlaybackController | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backdrop = backdrop
        self._music = music
        self._bridge = bridge
        self._prefs = preferences
        self._playback = playback
        self._pending_track_key: str | None = None
        self._shown_key: str | None = None
        self._track: Track | None = None
        self._eco = False
        self._paused_for_eco = False
        self._reload_pending = False
        self._reload_fails = 0
        self._last_reload_at = 0.0
        self._applied_quality: int | None = None
        self._looping = False
        self._video_armed = False
        self._excluded_itags: frozenset[str] = frozenset()
        self._drift_tolerance = WALLPAPER_SYNC_DRIFT_MS

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(WALLPAPER_SYNC_INTERVAL_MS)
        self._sync_timer.timeout.connect(self._sync_to_audio)

        backdrop.set_position_provider(self._audio_position_ms)

        preferences.changed.connect(self._on_preferences_changed)
        event_bus.track_changed.connect(self._on_track_changed)
        event_bus.playback_paused.connect(self._on_audio_paused)
        event_bus.playback_resumed.connect(self._on_audio_resumed)
        event_bus.playback_seeked.connect(self._on_audio_seeked)
        backdrop.stream_stalled.connect(self._on_stream_stalled)
        if playback is not None:
            hook = getattr(playback.player, "on_source_changed", None)
            if callable(hook):
                hook(self._on_audio_source)
        self._apply_enabled()
        self._apply_render_prefs()
        self._applied_quality = self._prefs.dynamic_wallpaper_quality

    def set_eco(self, enabled: bool) -> None:
        """В фоне останавливаем декод видео-обоев (дорого для GPU)."""
        if self._eco == enabled:
            return
        self._eco = enabled
        if enabled:
            self._sync_timer.stop()
            self._backdrop.follow_media_player(None)
            if self._backdrop.is_video_playing():
                self._backdrop.pause_video()
                self._paused_for_eco = True
        elif self._paused_for_eco:
            self._paused_for_eco = False
            if self._track is not None and self._video_should_play():
                self._on_track_changed(self._track)

    def _on_preferences_changed(self) -> None:
        self._apply_enabled()
        quality = self._prefs.dynamic_wallpaper_quality
        self._apply_render_prefs()
        need_reload = (
            self._applied_quality is not None
            and quality != self._applied_quality
            and self._prefs.dynamic_wallpaper_enabled
            and not self._eco
            and self._track is not None
        )
        self._applied_quality = quality
        if need_reload:
            self._shown_key = None
            self._on_track_changed(self._track)

    def _apply_render_prefs(self) -> None:
        quality = self._prefs.dynamic_wallpaper_quality
        self._backdrop.set_video_limits(
            fps=self._prefs.dynamic_wallpaper_fps,
            max_side=wallpaper_decode_max_side(quality),
        )

    def refresh_for_track(self, track: Track | None) -> None:
        enabled = self._prefs.dynamic_wallpaper_enabled
        if track is not None and enabled and not self._eco:
            self._on_track_changed(track)

    def _apply_enabled(self) -> None:
        enabled = self._prefs.dynamic_wallpaper_enabled
        self._backdrop.set_dynamic_wallpaper_enabled(enabled)
        if not enabled:
            self._pending_track_key = None
            self._shown_key = None
            self._track = None
            self._paused_for_eco = False
            self._video_armed = False
            self._sync_timer.stop()

    def _video_should_play(self) -> bool:
        if not self._prefs.dynamic_wallpaper_enabled or self._eco:
            return False
        if self._playback is not None:
            if not self._playback.audio_live:
                return False
            if not self._playback.player.is_playing():
                return False
        return True

    def _on_audio_source(self, source: str) -> None:
        if self._track is None or self._eco:
            return
        if not self._prefs.dynamic_wallpaper_enabled:
            return
        if wallpaper_source_meets_quality(
            source, self._prefs.dynamic_wallpaper_quality
        ):
            self._try_follow_audio(self._track)

    def _audio_position_ms(self) -> int:
        if self._playback is None:
            return 0
        return max(0, int(self._playback.player.time))

    def _on_audio_paused(self) -> None:
        self._sync_timer.stop()
        if not self._backdrop.is_following_audio_player():
            if self._backdrop.is_video_playing():
                self._backdrop.pause_video()

    def _on_audio_resumed(self) -> None:
        if self._video_armed and self._track is not None:
            if self._try_follow_audio(self._track):
                return
            self._start_video_load(self._track)
        if not self._video_should_play():
            return
        if self._backdrop.is_following_audio_player():
            return
        self._backdrop.resume_video()
        self._align_to_audio()
        self._sync_timer.start()

    def _on_audio_seeked(self, position_ms: int) -> None:
        """Перемотка трека — фон догоняет сразу, а не через такт таймера."""
        if self._looping or not self._prefs.dynamic_wallpaper_enabled or self._eco:
            return
        if self._backdrop.is_following_audio_player():
            return
        if not self._backdrop.is_video_playing():
            return
        self._drift_tolerance = WALLPAPER_SYNC_DRIFT_MS
        self._backdrop.seek_ms(max(0, int(position_ms)))

    def _align_to_audio(self) -> None:
        if self._looping or self._backdrop.is_following_audio_player():
            return
        if not self._backdrop.is_video_playing():
            return
        audio_ms = self._audio_position_ms()
        if audio_ms > 0:
            self._backdrop.seek_ms(audio_ms)

    def _sync_to_audio(self) -> None:
        if self._reload_pending or self._looping or not self._video_should_play():
            return
        if self._backdrop.is_following_audio_player():
            return
        if not self._backdrop.is_video_playing():
            return
        audio_ms = self._audio_position_ms()
        video_ms = self._backdrop.position_ms()
        if not wallpaper_positions_drifted(
            audio_ms, video_ms, tolerance_ms=self._drift_tolerance
        ):
            self._drift_tolerance = WALLPAPER_SYNC_DRIFT_MS
            return
        self._drift_tolerance = wallpaper_next_drift_tolerance(
            self._drift_tolerance, video_advancing=video_ms > 500
        )
        self._backdrop.seek_ms(audio_ms)

    def _on_track_changed(self, track: Track) -> None:
        if not self._prefs.dynamic_wallpaper_enabled or self._eco:
            return
        track_key = _track_key(track)
        self._track = track
        if track_key == self._shown_key and self._backdrop.is_video_playing():
            if (
                not self._looping
                and not self._backdrop.is_following_audio_player()
                and self._video_should_play()
                and not self._sync_timer.isActive()
            ):
                self._sync_timer.start()
            return
        self._pending_track_key = track_key
        self._reload_fails = 0
        self._looping = False
        self._excluded_itags = frozenset()
        self._drift_tolerance = WALLPAPER_SYNC_DRIFT_MS
        self._sync_timer.stop()
        cover = self._existing_cover_path(track)
        if cover is not None:
            self._backdrop.show_still(cover)
            self._shown_key = track_key
        self._video_armed = True
        if should_fetch_wallpaper_now(
            local=self._local_video_path(track) is not None,
            audio_live=self._video_should_play(),
        ):
            self._start_video_load(track)

    def _start_video_load(self, track: Track) -> None:
        self._video_armed = False
        if self._try_follow_audio(track):
            return
        self._bridge.schedule(self._load_video(track))

    def _on_stream_stalled(self) -> None:
        if self._eco or self._track is None or self._reload_pending:
            return
        now = monotonic()
        if now - self._last_reload_at < 3:
            return
        self._bridge.schedule(self._reload_video(self._track))

    async def _load_video(self, track: Track) -> None:
        track_key = _track_key(track)
        if self._try_follow_audio(track):
            return
        try:
            local_path = self._local_video_path(track)
            if local_path is not None:
                logger.info("Динамические обои: локальный файл %s", local_path)
                self._play_stream(track_key, local_path, loop=True)
                return

            url, duration = await self._music.streamer.get_video_info(
                track,
                finder=self._music.finder,
                height=self._prefs.dynamic_wallpaper_quality,
                exclude_itags=self._wallpaper_exclude_itags(),
            )
        except Exception:
            logger.exception("Не удалось получить видео для обоев: %s", track)
            if self._try_follow_audio(track, require_quality=False):
                return
            await self._show_cover(track, track_key)
            return

        if self._pending_track_key != track_key:
            return
        if url:
            logger.info(
                "Динамические обои: стрим %ss для %s", duration or "?", track
            )
            self._play_stream(track_key, url, loop=False)
            return

        if self._try_follow_audio(track, require_quality=False):
            return

        logger.warning("Видео для обоев не найдено: %s", track)
        await self._show_cover(track, track_key)

    async def _reload_video(self, track: Track) -> None:
        track_key = _track_key(track)
        if self._pending_track_key != track_key:
            return
        self._reload_pending = True
        self._last_reload_at = monotonic()
        try:
            url, _duration = await self._music.streamer.get_video_info(
                track,
                finder=self._music.finder,
                height=self._prefs.dynamic_wallpaper_quality,
                exclude_itags=self._wallpaper_exclude_itags(),
            )
            if self._pending_track_key != track_key:
                return
            if not url:
                self._reload_fails += 1
                if self._try_follow_audio(track, require_quality=False):
                    return
                if self._reload_fails >= 3:
                    await self._show_cover(track, track_key)
                return
            logger.info("Динамические обои: новый URL с позиции аудио для %s", track)
            self._play_stream(track_key, url, loop=False)
        except Exception:
            logger.exception("Не удалось обновить видео-фон: %s", track)
            self._reload_fails += 1
            if self._try_follow_audio(track, require_quality=False):
                return
            if self._reload_fails >= 3:
                await self._show_cover(track, track_key)
        finally:
            self._reload_pending = False

    async def _show_cover(self, track: Track, track_key: str) -> None:
        path = self._existing_cover_path(track)
        if path is None:
            try:
                await self._music.downloader.ensure_cover(track)
            except Exception:
                logger.debug("Обложка для обоев: %s", track, exc_info=True)
            path = self._existing_cover_path(track)
        if self._pending_track_key != track_key:
            return
        if path is None:
            return
        still = path
        self._play_on_main(track_key, lambda: self._backdrop.show_still(still))

    def _audio_source(self) -> str:
        if self._playback is None:
            return ""
        return str(getattr(self._playback.player, "current_source", "") or "")

    def _audio_media_player(self):
        if self._playback is None:
            return None
        return getattr(self._playback.player, "media_player", None)

    def _try_follow_audio(self, track: Track, *, require_quality: bool = True) -> bool:
        host = self._audio_media_player()
        source = self._audio_source()
        if host is None:
            return False
        if require_quality:
            if not wallpaper_source_meets_quality(
                source, self._prefs.dynamic_wallpaper_quality
            ):
                return False
        elif not wallpaper_source_has_video(source):
            return False
        track_key = _track_key(track)
        self._video_armed = False
        self._looping = False
        self._pending_track_key = track_key
        self._backdrop.follow_media_player(host)
        self._shown_key = track_key
        self._sync_timer.stop()
        logger.info("Динамические обои: кадры текущего потока, без второго URL")
        return True

    def _wallpaper_exclude_itags(self) -> frozenset[str]:
        itags = set(self._excluded_itags)
        current = wallpaper_url_itag(self._audio_source())
        if current:
            itags.add(current)
        return frozenset(itags)

    def _play_stream(self, track_key: str, url: str, *, loop: bool) -> None:
        def _run() -> None:
            if self._pending_track_key != track_key:
                return
            if wallpaper_stream_conflicts(self._audio_source(), url):
                itag = wallpaper_url_itag(url)
                logger.info(
                    "Видео-фон: тот же itag, что и аудио (%s) — ищем video-only",
                    itag or "?",
                )
                if (
                    itag
                    and self._track is not None
                    and itag not in self._excluded_itags
                ):
                    self._excluded_itags = self._excluded_itags | {itag}
                    self._start_video_load(self._track)
                    return
                if self._track is not None:
                    self._try_follow_audio(self._track, require_quality=False)
                return
            self._looping = loop
            # Короткий локальный клип крутится по кругу — к позиции трека его
            # привязывать нельзя, иначе перемотка выкинет за конец файла.
            self._backdrop.play_video_url(
                url,
                loop=loop,
                start_ms=0 if loop else self._audio_position_ms(),
                follow_audio=not loop,
                hold_until_audio=not loop and not self._video_should_play(),
            )
            self._shown_key = track_key
            self._reload_fails = 0
            self._drift_tolerance = WALLPAPER_SYNC_DRIFT_MS
            if not loop and self._video_should_play():
                self._sync_timer.start()
            else:
                self._sync_timer.stop()

        self._bridge.invoke_main(_run)

    def _play_on_main(self, track_key: str, play) -> None:
        def _run() -> None:
            if self._pending_track_key != track_key:
                return
            play()
            self._looping = False
            self._sync_timer.stop()
            self._shown_key = track_key

        self._bridge.invoke_main(_run)

    @staticmethod
    def _existing_cover_path(track: Track) -> str | None:
        path = Path(PathProvider().get_cover_path(track))
        if path.is_file() and path.stat().st_size > 0:
            return str(path)
        return None

    def _local_video_path(self, track: Track) -> str | None:
        for ext in ("mp4", "webm", "mkv"):
            path = Path(PathProvider().get_video_cache_path(track, extension=ext))
            if not path.is_file():
                continue
            size = path.stat().st_size
            if should_play_local_wallpaper(size):
                return str(path.resolve())
        return None
