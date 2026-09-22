from __future__ import annotations

import inspect
import logging
from pathlib import Path

from quantis.core.async_bridge import AsyncBridge
from quantis.models import Track
from quantis.models.playlist import RecommendationPlaylist, WavePlaylist
from quantis.models.repeat_mode import RepeatMode
from quantis.player import Player
from quantis.plugins.event_bus import EventBus
from quantis.providers import PlaylistManager
from quantis.services import MusicService, TrackHistoryService
from quantis.ui.preferences import UiPreferences

logger = logging.getLogger(__name__)

_MAX_RECOVERIES = 3
_MAX_FAILOVERS = 3
# Столько отыгранных миллисекунд считаем доказательством, что связь жива.
_HEALTHY_POSITION_MS = 15_000


class PlaybackController:
    """Медиатор логики воспроизведения."""

    def __init__(
        self,
        player: Player,
        playlist_manager: PlaylistManager,
        music_service: MusicService,
        event_bus: EventBus | None = None,
        history: TrackHistoryService | None = None,
        async_bridge: AsyncBridge | None = None,
    ) -> None:
        self.player = player
        self.playlist_manager = playlist_manager
        self.music = music_service
        self._event_bus = event_bus
        self._history = history
        self._bridge = async_bridge
        self._current_track: Track | None = None
        self._wave_skip_start_feedback = False
        self._stream_retry_pending = False
        self._stall_recoveries = 0
        self._stall_track_key: str | None = None
        self._failovers = 0
        self._play_seq = 0
        self._seek_seq = 0
        self._seek_pending = False
        self._audio_live = False
        self._repeat_mode = UiPreferences().repeat_mode

    @property
    def repeat_mode(self) -> RepeatMode:
        return self._repeat_mode

    def cycle_repeat_mode(self) -> RepeatMode:
        self._repeat_mode = self._repeat_mode.cycle()
        UiPreferences().set_repeat_mode(self._repeat_mode)
        return self._repeat_mode

    async def handle_track_finished(self) -> None:
        if self.repeat_mode is RepeatMode.TRACK:
            track = self._current_track
            if track is not None:
                await self.play_track(track)
            return
        await self.play_next()

    @property
    def is_seeking(self) -> bool:
        return self._seek_pending

    @property
    def audio_live(self) -> bool:
        """True, когда текущий трек реально запущен в движке, а не только объявлен."""
        return self._audio_live

    def notify_progress(self, position_ms: int) -> None:
        """Трек играет достаточно долго — цепочку аварийных пропусков сбрасываем."""
        if position_ms >= _HEALTHY_POSITION_MS:
            self._failovers = 0
        report = getattr(self.music.streamer, "report_position_ms", None)
        track = self._current_track
        if callable(report) and track is not None:
            report(track, position_ms)

    def handle_stream_error(self, message: str) -> None:
        """Повтор воспроизведения при ошибке медиадвижка."""
        paused_at = getattr(self.player, "paused_at_ms", 0) or 0
        known = getattr(self.player, "last_known_ms", 0) or 0
        position = max(0, int(self.player.time), int(paused_at), int(known))
        self.request_playback_recovery(position, reason=message)

    def request_playback_recovery(
        self, position_ms: int, *, reason: str = "stall"
    ) -> None:
        if self._stream_retry_pending or self._bridge is None:
            return
        self._bridge.schedule(self.recover_playback(position_ms, reason=reason))

    async def recover_playback(
        self, position_ms: int, *, reason: str = "stall"
    ) -> None:
        """Обновляет источник и продолжает с текущей позиции (signed URL / обрыв CDN)."""
        if self._stream_retry_pending:
            return
        track = self._current_track
        if track is None:
            return

        source = self.player.current_source
        if source and not str(source).startswith(("http://", "https://")):
            path = Path(str(source))
            # stat локального файла — микросекунды, в поток не выносим
            if track.downloaded and path.is_file():  # noqa: ASYNC240
                return

        track_key = f"{track.source}:{track.track_id}"
        if self._stall_track_key != track_key:
            self._stall_track_key = track_key
            self._stall_recoveries = 0
        if reason in ("resume-after-pause", "seek"):
            self._stall_recoveries = 0
        if self._stall_recoveries >= _MAX_RECOVERIES:
            logger.warning(
                "Лимит восстановления потока для «%s» (%s) — следующий трек",
                track.title,
                reason,
            )
            await self._failover_to_next()
            return

        self._stream_retry_pending = True
        self._stall_recoveries += 1
        try:
            logger.info(
                "Восстановление потока «%s» @ %dms (%s)",
                track.title,
                position_ms,
                reason,
            )
            self.music.streamer.invalidate(track)
            new_source = await self.music.streamer.open_playback(track)
            if not new_source:
                return

            resume_at = position_ms
            if resume_at < 8000:
                await self._wait_for_more_prefix(track)
            if resume_at > 0:
                await self._prepare_seek(track, resume_at, new_source)

            def replay() -> None:
                if self._current_track is not track:
                    return
                self._audio_live = True
                if resume_at > 0:
                    self.player.play(new_source, start_ms=resume_at)
                else:
                    self.player.play(new_source)

            self._bridge.invoke_main(replay)  # type: ignore[union-attr]
        except Exception:
            logger.exception("Не удалось восстановить поток")
        finally:
            self._stream_retry_pending = False

    async def _failover_to_next(self) -> None:
        """Трек не поднимается — не молчим, а переходим дальше по очереди."""
        if self._failovers >= _MAX_FAILOVERS:
            logger.warning("Подряд %d сбойных трека — остановка", self._failovers)
            return
        self._failovers += 1
        self._stall_track_key = None
        self._stall_recoveries = 0
        await self.play_next()

    async def _wait_for_more_prefix(self, track: Track) -> None:
        """После раннего EOF ждём ещё кусок буфера, а не крутим те же 2 секунды."""
        wait = getattr(self.music.streamer, "wait_for_more_prefix", None)
        if wait is None:
            return
        try:
            result = wait(track)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.debug("Ожидание докачки буфера не удалось", exc_info=True)

    async def _prepare_seek(
        self, track: Track, position_ms: int, source: str | None
    ) -> bool:
        """Ждёт, пока прогрессивный буфер догрузит нужный участок."""
        seek = getattr(self.music.streamer, "seek_to_ms", None)
        if seek is None:
            return True
        try:
            result = seek(track, position_ms, source=source)
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, bool):
                return result
            return True
        except Exception:
            logger.debug("Подготовка перемотки не удалась", exc_info=True)
            return False

    def seek(self, position_ms: int) -> None:
        """Единая точка перемотки: буфер, плеер и видео-фон идут вместе."""
        position = max(0, int(position_ms))
        duration = max(0, int(self.player.duration))
        if duration > 2000 and position >= duration - 1500:
            notify = getattr(self.player, "notify_natural_end", None)
            if callable(notify):
                notify()
            return
        track = self._current_track
        self._seek_seq += 1
        seq = self._seek_seq
        self._seek_pending = True
        if track is None or self._bridge is None:
            self._apply_seek(position, seq=seq, track=track)
            return
        self._bridge.schedule(self._seek_buffered(track, position, seq))

    async def _seek_buffered(self, track: Track, position_ms: int, seq: int) -> None:
        ready = await self._prepare_seek(track, position_ms, self.player.current_source)
        if seq != self._seek_seq or self._current_track is not track:
            return
        if not ready:
            self._seek_pending = False
            self.request_playback_recovery(position_ms, reason="seek")
            return
        self._bridge.invoke_main(  # type: ignore[union-attr]
            lambda: self._apply_seek(position_ms, seq=seq, track=track)
        )

    def _apply_seek(
        self,
        position_ms: int,
        *,
        seq: int | None = None,
        track: Track | None = None,
    ) -> None:
        if seq is not None and seq != self._seek_seq:
            return
        if track is not None and self._current_track is not track:
            return
        self._seek_pending = False
        self.player.time = position_ms
        if self._event_bus is not None:
            self._event_bus.playback_seeked.emit(position_ms)

    async def _prefetch_next_track(self, current: Track) -> None:
        playlist = self.playlist_manager.current_playlist
        if playlist is None or len(playlist) == 0:
            return
        if isinstance(playlist, RecommendationPlaylist) and playlist.infinite:
            added = await self.music.recommendation.ensure_extended(playlist, current)
            if added:
                self._emit_queue_extended(playlist)
        tracks = playlist.tracks.values
        try:
            index = tracks.index(current)
        except ValueError:
            return
        if index + 1 >= len(tracks):
            return
        nxt = tracks[index + 1]
        await self.music.streamer.prefetch_stream(nxt)

    @property
    def current_track(self) -> Track | None:
        return self._current_track

    def _local_path_if_ready(self, track: Track) -> str | None:
        extension = getattr(track, "extension", None)
        path = (
            self.music.provider.get_track_path(track, extension)
            if extension
            else self.music.provider.get_track_path(track)
        )
        file_path = Path(path)
        if not file_path.is_file():
            return None
        try:
            if file_path.stat().st_size <= 0:
                return None
        except OSError:
            return None
        return path

    async def _resolve_source(self, track: Track) -> str | None:
        if track.downloaded:
            local = self._local_path_if_ready(track)
            if local:
                return local

        return await self.music.streamer.open_playback(track)

    def _begin_track(self, track: Track) -> None:
        """Сразу объявляет трек: UI и видео-фон стартуют параллельно с буфером."""
        self._seek_seq += 1
        self._seek_pending = False
        self._audio_live = False
        self._current_track = track
        self._stall_track_key = None
        self._stall_recoveries = 0

        def announce() -> None:
            # Иначе прошлый трек продолжает играть, а ползунок тикает его время,
            # пока yt-dlp резолвит YouTube.
            stop = getattr(self.player, "stop", None)
            if callable(stop):
                stop()
            self.player.current_track = track
            if self._event_bus is not None:
                self._event_bus.track_changed.emit(track)

        if self._bridge is not None:
            self._bridge.invoke_main(announce)
        else:
            announce()

    async def play_track(self, track: Track | None) -> None:
        if not track:
            return

        self._play_seq += 1
        seq = self._play_seq
        self._begin_track(track)

        source = await self._resolve_source(track)
        if seq != self._play_seq:
            return
        if not source:
            message = f"Не удалось получить источник для воспроизведения: {track.title}"
            logger.warning(message)
            if self._event_bus is not None:

                def notify() -> None:
                    self._event_bus.error_occurred.emit(message)

                if self._bridge is not None:
                    self._bridge.invoke_main(notify)
                else:
                    notify()
            return

        def start_playback() -> None:
            if seq != self._play_seq:
                return
            self._current_track = track
            self._stall_track_key = None
            self._stall_recoveries = 0
            self.player.current_track = track
            self._audio_live = True
            self.player.play(source)

        if self._bridge is not None:
            self._bridge.invoke_main(start_playback)
        else:
            start_playback()

        playlist = self.playlist_manager.current_playlist
        if isinstance(playlist, WavePlaylist) and not self._wave_skip_start_feedback:
            try:
                await self.music.wave.notify_track_started(track, playlist)
            except Exception:
                logger.debug("Wave start feedback не отправился", exc_info=True)

        if self._bridge is not None:
            self._bridge.schedule(self._prefetch_next_track(track))

    async def play_next(self) -> None:
        playlist = self.playlist_manager.current_playlist
        if playlist is None or len(playlist) == 0:
            return

        if isinstance(playlist, WavePlaylist) and playlist.source == "yandex":
            await self._play_wave_next(playlist)
            return

        if isinstance(playlist, RecommendationPlaylist) and playlist.infinite:
            await self._play_recommendation_next(playlist)
            return

        track = playlist.move_next_track()
        await self.play_track(track)

    async def _play_wave_next(self, playlist: WavePlaylist) -> None:
        finished = self._current_track
        if finished is None:
            try:
                finished = playlist.get_current_track()
            except Exception:
                finished = None
        if finished is None:
            return

        played_seconds = max(0.0, self.player.time / 1000.0)
        nxt = await self.music.wave.continue_after_finish(
            playlist,
            finished,
            played_seconds=played_seconds,
        )
        if nxt is None:
            logger.info("Моя волна: нет следующего трека")
            return

        self._wave_skip_start_feedback = True
        try:
            await self.play_track(nxt)
        finally:
            self._wave_skip_start_feedback = False

    async def _play_recommendation_next(self, playlist: RecommendationPlaylist) -> None:
        finished = self._current_track
        if finished is None:
            try:
                finished = playlist.get_current_track()
            except Exception:
                finished = None
        if finished is None:
            return

        before = len(playlist)
        nxt = await self.music.recommendation.continue_after_finish(playlist, finished)
        if nxt is None:
            logger.info("Рекомендации: нет следующего трека")
            return
        if len(playlist) > before:
            self._emit_queue_extended(playlist)
        await self.play_track(nxt)

    def _emit_queue_extended(self, playlist) -> None:
        if self._event_bus is None:
            return

        def emit() -> None:
            signal = getattr(self._event_bus, "queue_extended", None)
            if signal is not None:
                signal.emit(playlist)

        if self._bridge is not None:
            self._bridge.invoke_main(emit)
        else:
            emit()

    async def play_previous(self) -> None:
        playlist = self.playlist_manager.current_playlist
        if playlist is None or len(playlist) == 0:
            return
        track = playlist.move_previous_track()
        await self.play_track(track)

    def toggle_pause(self) -> None:
        self.player.toggle_pause()

    async def generate_radio(self, track: Track | None):
        if track:
            return await self.music.recommendation.generate_radio_from_track(track)
