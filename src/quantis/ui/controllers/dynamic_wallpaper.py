"""Динамические обои: видео текущего трека, в том числе часовые миксы.

Контроллер выбирает источник (кадры аудиоплеера, локальный клип, отдельный
поток, обложка) и раз в такт отдаёт позиции звука и видео ядру
``WallpaperSync``, а его команды исполняет на ``WallpaperBackdrop``.
"""

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
    should_fetch_wallpaper_now,
    should_play_local_wallpaper,
    wallpaper_decode_max_side,
    wallpaper_source_has_video,
    wallpaper_source_meets_quality,
    wallpaper_stream_conflicts,
    wallpaper_url_itag,
)
from quantis.services.wallpaper_sync import (
    SYNC_TICK_MS,
    AudioState,
    Command,
    CommandKind,
    WallpaperSync,
)
from quantis.ui.preferences import UiPreferences
from quantis.ui.views.widgets.wallpaper_backdrop import WallpaperBackdrop

logger = logging.getLogger(__name__)


# Сводка синхронизации в лог не чаще этого.
_REPORT_INTERVAL_S = 5.0
# Разница длительностей больше этой — скорее всего другой монтаж клипа.
_VERSION_GAP_MS = 1500
# Поток встал столько раз — берём другой формат (itag может быть битым).
_STALLS_BEFORE_NEW_FORMAT = 2
# ...а после стольких — сдаёмся и показываем обложку до смены трека.
_STALLS_BEFORE_COVER = 5
# Остановки реже этого не копим: на часовом миксе редкие подвисания — норма.
_STALL_MEMORY_S = 60.0


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
        self._video_armed = False
        self._excluded_itags: frozenset[str] = frozenset()

        self._sync = WallpaperSync()
        self._last_report_at = 0.0
        self._loading_key: str | None = None
        self._stalls = 0
        self._last_stall_at = 0.0
        self._reported_duration_for: str | None = None
        self._av_delay_ms = 0
        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(SYNC_TICK_MS)
        self._sync_timer.timeout.connect(self._tick)

        preferences.wallpaper_changed.connect(self._on_preferences_changed)
        event_bus.track_changed.connect(self._on_track_changed)
        event_bus.playback_paused.connect(self._on_audio_paused)
        event_bus.playback_resumed.connect(self._on_audio_resumed)
        event_bus.playback_seeked.connect(self._on_audio_seeked)
        backdrop.stream_stalled.connect(self._on_stream_stalled)
        backdrop.media_ready.connect(self._on_video_ready)
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
            # Ядро не гасим: после эко таймер поднимется и видео догонит звук.
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
            self._on_track_changed(self._track, force=True)

    def _apply_render_prefs(self) -> None:
        delay = int(self._prefs.dynamic_wallpaper_av_delay_ms)
        if delay != self._av_delay_ms:
            self._av_delay_ms = delay
            # Сдвиг поменялся — ядро выровняет видео заново, без ожидания.
            self._sync.audio_jumped()
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
            self._stop_sync()

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

    def _heard_position_ms(self, position_ms: int) -> int:
        """Что сейчас реально слышно: позиция плеера минус задержка выхода."""
        return max(0, int(position_ms) - self._av_delay_ms)

    def _audio_buffering(self) -> bool:
        if self._playback is None:
            return False
        return bool(self._playback.player.is_buffering())

    def _on_audio_paused(self) -> None:
        self._tick()

    def _on_audio_resumed(self) -> None:
        if self._video_armed and self._track is not None:
            if self._try_follow_audio(self._track):
                return
            self._start_video_load(self._track)
        self._tick()

    def _on_audio_seeked(self, position_ms: int) -> None:
        """Перемотка трека — видео догоняет сразу, а не через такт таймера."""
        self._sync.audio_jumped()
        self._tick(audio_ms=max(0, int(position_ms)))

    def _start_sync(self, *, loop: bool) -> None:
        self._sync.start(loop=loop)
        self._sync_timer.start()
        self._tick()

    def _stop_sync(self) -> None:
        self._sync_timer.stop()
        self._sync.stop()

    def _tick(self, audio_ms: int | None = None) -> None:
        """Один такт синхронизации: снимки звука и видео → команды фону."""
        if not self._sync.active or self._reload_pending:
            return
        video = self._backdrop.video_state()
        if video is None:
            return
        playing = self._video_should_play()
        raw_ms = self._audio_position_ms() if audio_ms is None else audio_ms
        audio = AudioState(
            position_ms=self._heard_position_ms(raw_ms),
            playing=playing,
            buffering=playing and self._audio_buffering(),
        )
        commands = self._sync.tick(audio, video)
        self._report(audio, video)
        for command in commands:
            self._apply_command(command)

    def _report(self, audio: AudioState, video) -> None:
        """Раз в несколько секунд — сводка для диагностики рассинхрона."""
        now = monotonic()
        if now - self._last_report_at < _REPORT_INTERVAL_S:
            return
        if not audio.playing or not video.ready:
            return
        self._last_report_at = now
        logger.info(
            "Синхр. фона: звук %d, видео %d, Δ=%+d мс, скорость %.3f, "
            "упреждение %d, задержка звука %d, буфер звук/видео %s/%s",
            audio.position_ms,
            video.position_ms,
            audio.position_ms - video.position_ms,
            self._sync.rate,
            self._sync.lead_ms,
            self._av_delay_ms,
            audio.buffering,
            video.buffering,
        )

    def _on_video_ready(self) -> None:
        video = self._backdrop.video_state()
        source = self._backdrop.current_video_url()
        fresh = source != self._reported_duration_for
        if (
            fresh
            and video is not None
            and video.duration_ms > 0
            and self._playback is not None
        ):
            self._reported_duration_for = source
            audio_ms = int(self._playback.player.duration)
            if audio_ms > 0:
                gap = audio_ms - video.duration_ms
                log = logger.warning if abs(gap) > _VERSION_GAP_MS else logger.info
                log(
                    "Синхр. фона: длительность звук %d, видео %d (разница %+d мс)%s",
                    audio_ms,
                    video.duration_ms,
                    gap,
                    (
                        " — похоже, другая версия клипа"
                        if abs(gap) > _VERSION_GAP_MS
                        else ""
                    ),
                )
        self._tick()

    def _apply_command(self, command: Command) -> None:
        if command.kind is CommandKind.SEEK:
            self._backdrop.seek_ms(int(command.value))
        elif command.kind is CommandKind.RATE:
            self._backdrop.set_playback_rate(command.value)
        elif command.kind is CommandKind.PAUSE:
            self._backdrop.pause_video()
        elif command.kind is CommandKind.PLAY:
            self._backdrop.resume_video()

    def _on_track_changed(self, track: Track, *, force: bool = False) -> None:
        if not self._prefs.dynamic_wallpaper_enabled or self._eco:
            return
        track_key = _track_key(track)
        self._track = track
        # Тот же трек (рестарт потока, смена настроек, выход из эко) — фон уже
        # есть или грузится. Сломанный поток чинит stall → reload, не мы.
        if not force and track_key == self._pending_track_key:
            if self._sync.active and not self._sync_timer.isActive():
                self._sync_timer.start()
            return
        logger.info("Динамические обои: новый трек %s", track)
        self._pending_track_key = track_key
        self._reload_fails = 0
        self._stalls = 0
        self._loading_key = None
        self._excluded_itags = frozenset()
        self._stop_sync()
        cover = self._existing_cover_path(track)
        if cover is not None:
            self._backdrop.show_still(cover)
            self._shown_key = track_key
        else:
            # Кадры прошлого трека под новым звуком хуже пустого фона.
            self._backdrop.pause_video()
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
        track_key = _track_key(track)
        if self._loading_key == track_key:
            return
        self._loading_key = track_key
        self._bridge.schedule(self._load_video(track))

    def _on_stream_stalled(self) -> None:
        if self._eco or self._track is None or self._reload_pending:
            return
        now = monotonic()
        if now - self._last_reload_at < 3:
            return
        if now - self._last_stall_at > _STALL_MEMORY_S:
            self._stalls = 0
        self._last_stall_at = now
        self._stalls += 1
        itag = wallpaper_url_itag(self._backdrop.current_video_url())
        if self._stalls >= _STALLS_BEFORE_COVER:
            logger.warning(
                "Видео-фон: поток встаёт %d раз подряд — показываем обложку",
                self._stalls,
            )
            self._stop_sync()
            track = self._track
            self._bridge.schedule(self._show_cover(track, _track_key(track)))
            return
        if self._stalls >= _STALLS_BEFORE_NEW_FORMAT and itag:
            logger.info("Видео-фон: itag %s не тянется — пробуем другой формат", itag)
            self._excluded_itags = self._excluded_itags | {itag}
        self._last_reload_at = now
        self._bridge.schedule(self._reload_video(self._track))

    async def _load_video(self, track: Track) -> None:
        track_key = _track_key(track)
        try:
            await self._load_video_once(track, track_key)
        finally:
            if self._loading_key == track_key:
                self._loading_key = None

    async def _load_video_once(self, track: Track, track_key: str) -> None:
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
            logger.info("Динамические обои: стрим %ss для %s", duration or "?", track)
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
        self._pending_track_key = track_key
        self._stop_sync()
        self._backdrop.follow_media_player(host)
        self._shown_key = track_key
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
            # Короткий локальный клип крутится по кругу — к позиции трека его
            # не привязываем, только ставим на паузу вместе со звуком.
            # Поток ждёт на паузе, пока ядро не перемотает его к звуку.
            self._backdrop.play_video_url(
                url, loop=loop, autoplay=loop and self._video_should_play()
            )
            self._shown_key = track_key
            self._reload_fails = 0
            self._start_sync(loop=loop)

        self._bridge.invoke_main(_run)

    def _play_on_main(self, track_key: str, play) -> None:
        def _run() -> None:
            if self._pending_track_key != track_key:
                return
            self._stop_sync()
            play()
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
