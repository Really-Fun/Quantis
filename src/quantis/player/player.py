"""Контроллер воспроизведения: play / pause / volume / seek."""

from __future__ import annotations

import logging
from time import monotonic
from typing import Callable

from quantis.models import Track
from quantis.player.base import MediaEngine
from quantis.player.factory import create_media_engine

logger = logging.getLogger(__name__)


def resolve_playback_duration(engine_ms: int, catalog_ms: int) -> int:
    """Длина для UI: каталог — истина, движок только слегка уточняет.

    Qt на HTTP часто врёт: то 6 с на недокачанном файле, то 24 ч на googlevideo.
    max(engine, catalog) залипал завышенную оценку в ползунке.
    """
    engine_ms = max(0, int(engine_ms))
    catalog_ms = max(0, int(catalog_ms))
    if catalog_ms <= 0:
        return engine_ms
    if engine_ms <= 0:
        return catalog_ms
    slack = max(2000, int(catalog_ms * 0.15))
    if catalog_ms <= engine_ms <= catalog_ms + slack:
        return engine_ms
    if engine_ms < catalog_ms:
        wild_catalog = catalog_ms >= max(
            engine_ms * 2, engine_ms + 30 * 60 * 1000
        ) and engine_ms >= 30_000
        return engine_ms if wild_catalog else catalog_ms
    return catalog_ms


class Player:
    """Плеер. Работает со строками (локальные файлы / URL потока)."""

    def __init__(self, engine: MediaEngine | None = None) -> None:
        self._engine: MediaEngine = engine or create_media_engine()

        self.current_source: str | None = None
        self.current_track: Track | None = None
        self.on_pause: bool = False
        self._paused_at_ms: int = 0
        self._paused_at_mono: float = 0.0
        self._playback_active: bool = False
        self._loading_source: bool = False
        self._was_playing: bool = False
        self._finish_emitted: bool = False
        self._last_known_ms: int = 0
        self._stale_position_ms: int = 0

        self._source_changed_callbacks: list[Callable[[str], None]] = []
        self._playback_paused_callbacks: list[Callable[[], None]] = []
        self._playback_resumed_callbacks: list[Callable[[], None]] = []
        self._track_finished_callbacks: list[Callable[[], None]] = []
        self._next_callbacks: list[Callable[[], None]] = []
        self._previous_callbacks: list[Callable[[], None]] = []
        self._stream_error_callbacks: list[Callable[[str], None]] = []

        self._engine.on_playing(self._on_engine_playing)
        self._engine.on_paused(self._on_engine_paused)
        self._engine.on_stopped(self._on_engine_stopped)
        self._engine.on_ended(self._on_engine_ended)
        self._stream_retry_used = False
        self._engine.on_error(self._on_engine_error)

    def on_source_changed(self, callback: Callable[[str], None]) -> None:
        self._source_changed_callbacks.append(callback)

    def on_playback_paused(self, callback: Callable[[], None]) -> None:
        self._playback_paused_callbacks.append(callback)

    def on_playback_resumed(self, callback: Callable[[], None]) -> None:
        self._playback_resumed_callbacks.append(callback)

    def on_track_finished(self, callback: Callable[[], None]) -> None:
        self._track_finished_callbacks.append(callback)

    def on_next_requested(self, callback: Callable[[], None]) -> None:
        self._next_callbacks.append(callback)

    def on_previous_requested(self, callback: Callable[[], None]) -> None:
        self._previous_callbacks.append(callback)

    def on_stream_error(self, callback: Callable[[str], None]) -> None:
        self._stream_error_callbacks.append(callback)

    def on_audio_buffer(self, callback: Callable) -> None:
        hook = getattr(self._engine, "on_audio_buffer", None)
        if callable(hook):
            hook(callback)

    def play(self, source: str, *, start_ms: int = 0) -> None:
        self._stream_retry_used = False
        previous = max(
            0,
            int(self._engine.get_position_ms()),
            int(self._last_known_ms),
        )
        resume_at = max(0, int(start_ms))
        self._loading_source = True
        self._finish_emitted = False
        # Пока setSource не сбросил движок, он ещё отдаёт хвост прошлого трека.
        if resume_at > 0 and abs(previous - resume_at) <= 2000:
            self._stale_position_ms = 0
        else:
            self._stale_position_ms = previous if previous > 1500 else 0
        self._last_known_ms = resume_at
        # Сессия активна сразу: иначе EndReached до PlayingState глушит
        # автопереход (типично для VLC на HTTP).
        self._playback_active = True
        self._was_playing = False
        self.on_pause = False
        self._paused_at_ms = 0
        self._paused_at_mono = 0.0
        self.current_source = source
        self._engine.play_media(source)
        if start_ms > 0:
            self._request_seek(start_ms)
        for callback in self._source_changed_callbacks:
            callback(source)

    def pause(self) -> None:
        if not self.current_source:
            return
        position = max(0, self.time)
        if position > 0:
            self._paused_at_ms = position
        self._paused_at_mono = monotonic()
        self.on_pause = True
        self._engine.pause_media()
        for callback in self._playback_paused_callbacks:
            callback()

    def resume(self) -> None:
        if not self.current_source:
            return
        resume_at = max(0, self._paused_at_ms, self.time)
        if self._http_source_likely_stale(resume_at):
            logger.info(
                "HTTP-поток после паузы — обновление источника @ %dms",
                resume_at,
            )
            for callback in self._stream_error_callbacks:
                callback("resume-after-pause")
            return
        self.on_pause = False
        self._engine.resume_media()
        if resume_at > 1000:
            self._request_seek(resume_at)
        self._paused_at_ms = 0
        self._paused_at_mono = 0.0
        for callback in self._playback_resumed_callbacks:
            callback()

    def stop(self) -> None:
        self.on_pause = True
        self._paused_at_ms = 0
        self._paused_at_mono = 0.0
        self._playback_active = False
        self._was_playing = False
        self._finish_emitted = True
        self._engine.stop_media()
        for callback in self._playback_paused_callbacks:
            callback()

    def toggle_pause(self) -> None:
        if not self.current_source:
            return
        if self.is_playing():
            self.pause()
        else:
            self.resume()

    def next(self) -> None:
        for callback in self._next_callbacks:
            callback()

    def previous(self) -> None:
        for callback in self._previous_callbacks:
            callback()

    def is_playing(self) -> bool:
        return self._engine.is_playing()

    def is_buffering(self) -> bool:
        check = getattr(self._engine, "is_buffering", None)
        if callable(check):
            return bool(check())
        return False

    def _on_engine_playing(self) -> None:
        previous = self._was_playing
        # Не снимаем _loading_source здесь: PlayingState приходит до реального
        # прогресса, а следом часто летит ложный EndReached.
        self.on_pause = False
        self._playback_active = True
        self._was_playing = True
        if not previous:
            for callback in self._playback_resumed_callbacks:
                callback()

    def _on_engine_paused(self) -> None:
        was_playing = self._was_playing
        self.on_pause = True
        self._was_playing = False
        if self._playback_active and not self._loading_source and was_playing:
            for callback in self._playback_paused_callbacks:
                callback()

    def _on_engine_stopped(self) -> None:
        self._was_playing = False
        if self._loading_source:
            return
        self.on_pause = True

    def notify_natural_end(self) -> None:
        """Запасной путь, если движок не прислал EndReached."""
        self._on_engine_ended()

    def _emit_track_finished(self) -> None:
        if self._finish_emitted:
            return
        self._finish_emitted = True
        self._playback_active = False
        self._was_playing = False
        for callback in self._track_finished_callbacks:
            callback()

    def _on_engine_ended(self) -> None:
        if not self._playback_active or not self.current_source:
            return
        if self._finish_emitted:
            return
        # EndReached предыдущего источника при set_media — Playing ещё не было.
        if self._loading_source and not self._was_playing and self._last_known_ms < 1000:
            return
        duration = self.duration
        position = self.time
        if position < 1000:
            position = max(position, self._last_known_ms)
        is_http = str(self.current_source).startswith(("http://", "https://"))
        # ~30с preview на прямом HTTP. Локальный growing MP3 на этом окне
        # восстанавливаем, а не считаем трек законченным.
        truncated = is_http and duration > 60_000 and 15_000 <= position <= 45_000
        near_end = duration > 0 and position >= duration - 2000
        # Раньше time≈0 после EndReached считали концом. VLC/Qt так сбрасывают
        # и в начале: трек «пчик» — и плейлист срывается дальше.
        little_progress = position < 3000 and (
            duration <= 0 or position < max(3000, int(duration * 0.15))
        )
        if little_progress and not near_end and not truncated:
            logger.warning(
                "Поток оборвался в начале (%sms из %sms) — восстановление",
                position,
                duration,
            )
            for callback in self._stream_error_callbacks:
                callback("ended-early")
            return
        early = (
            duration > 1000
            and not near_end
            and not truncated
            and position < duration - 1000
        )
        if early:
            logger.warning(
                "Поток оборвался рано (%sms из %sms) — восстановление",
                position,
                duration,
            )
            for callback in self._stream_error_callbacks:
                callback("ended-early")
            return
        if truncated:
            logger.warning(
                "Поток оборвался рано (%sms из %sms) — preview или обрыв CDN",
                position,
                duration,
            )
        self._emit_track_finished()

    def _on_engine_error(self, message: str) -> None:
        logger.warning(
            "MediaEngine error=%s source=%s",
            message,
            self.current_source,
        )
        for callback in self._stream_error_callbacks:
            callback(message)

    def _request_seek(self, ms: int) -> None:
        engine = self._engine
        request = getattr(engine, "request_seek", None)
        if callable(request):
            request(ms)
        else:
            engine.set_position_ms(ms)

    @property
    def last_known_ms(self) -> int:
        """Последняя живая позиция: после EndOfMedia Qt часто сбрасывает time в 0."""
        return max(0, int(self._last_known_ms))

    @property
    def paused_at_ms(self) -> int:
        return max(0, self._paused_at_ms)

    def paused_for_sec(self) -> float:
        if self._paused_at_mono <= 0:
            return 0.0
        return max(0.0, monotonic() - self._paused_at_mono)

    def _http_source_likely_stale(self, resume_at: int) -> bool:
        source = self.current_source or ""
        if not str(source).startswith(("http://", "https://")):
            return False
        if resume_at <= 1000:
            return False
        if self.paused_for_sec() >= 15.0:
            return True
        return self.time < 1000

    @property
    def volume(self) -> int:
        return self._engine.get_volume()

    @volume.setter
    def volume(self, value: int) -> None:
        self._engine.set_volume(value)

    def duck_gain(self) -> float:
        getter = getattr(self._engine, "get_duck_gain", None)
        if callable(getter):
            return float(getter())
        return 1.0

    def set_duck_gain(self, gain: float) -> None:
        setter = getattr(self._engine, "set_duck_gain", None)
        if callable(setter):
            setter(gain)

    @property
    def time(self) -> int:
        position = max(0, int(self._engine.get_position_ms()))
        if self._loading_source:
            stale = max(0, self._stale_position_ms)
            if stale > 1500 and abs(position - stale) <= 2000:
                return max(0, self._last_known_ms)
            if position > 500:
                self._last_known_ms = position
                self._loading_source = False
                self._stale_position_ms = 0
            return position
        if position > 500:
            self._last_known_ms = position
        return position

    @time.setter
    def time(self, time_in_ms: int) -> None:
        position = max(0, int(time_in_ms))
        self._last_known_ms = position
        # Через request_seek: движок доложит позицию, когда медиа готово.
        self._request_seek(position)
        if position == 0:
            self._engine.set_position_ms(0)

    @property
    def duration(self) -> int:
        engine_ms = max(0, int(self._engine.get_duration_ms()))
        catalog_ms = 0
        track = self.current_track
        if track is not None:
            catalog_ms = max(0, int(getattr(track, "duration_ms", 0) or 0))
        return resolve_playback_duration(engine_ms, catalog_ms)
