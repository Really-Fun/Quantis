"""Ядро синхронизации видео-фона с треком.

Звук — ведущие часы, видео — ведомое. Каждый такт ядро сравнивает позиции и
выдаёт команды для видеоплеера:

* пауза или буферизация звука — видео стоит, старт звука — видео идёт;
* мелкое расхождение убирается скоростью видео (±8 %): без рывков и без
  перезапроса HTTP-потока;
* видео впереди — ждёт на паузе, пока звук догонит: это бесплатно, а
  перемотка назад на HTTP — новый запрос к CDN;
* видео отстаёт — перемотка с упреждением: видео прыгает туда, где будет
  звук, когда декодер выйдет из буферизации. Упреждение подстраивается по
  результату удачных перемоток;
* неудачная перемотка включает паузу между попытками (2, 4, 8… с): каждая
  перемотка отнимает канал у звука;
* звук завис (позиция не растёт) — видео тоже стоит;
* клип короче трека замирает на последнем кадре, а не перематывается по кругу.

Модуль без Qt: на вход — снимки состояния, на выход — команды.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from time import monotonic

SYNC_TICK_MS = 200
# Меньше этого глаз не замечает, а скорость дёргать незачем.
DEADBAND_MS = 40
# До этого порога догоняем скоростью, дальше — перемоткой или ожиданием.
SOFT_LIMIT_MS = 1000
# Видео впереди не дальше этого — ставим на паузу и ждём звук.
AHEAD_WAIT_MS = 6000
# За сколько миллисекунд трека хотим съесть расхождение скоростью.
CORRECTION_WINDOW_MS = 2500
MAX_RATE_DELTA = 0.08
RATE_STEP = 0.005
INITIAL_SEEK_LEAD_MS = 300
MAX_SEEK_LEAD_MS = 2000
# Доля остатка после перемотки, на которую правим упреждение.
LEAD_LEARN_RATE = 0.6
# Учимся только на перемотках, которые уложились в это время: долгие —
# это перегруженный канал, а не задержка декодера.
LEAD_LEARN_MAX_SETTLE_S = 3.0
LEAD_LEARN_MAX_RESIDUAL_MS = 1000
# Перемотка считается завершённой, когда видео ушло вперёд от цели на столько.
SETTLE_PROGRESS_MS = 150
SETTLE_TIMEOUT_S = 5.0
SEEK_BACKOFF_BASE_S = 2.0
SEEK_BACKOFF_MAX_S = 30.0
# Ближе к концу клипа не перематываем: Qt на googlevideo ловит EndOfMedia.
END_GUARD_MS = 400
# VLC отдаёт позицию ступеньками: между ними досчитываем, но не дальше этого.
CLOCK_MAX_EXTRAPOLATION_MS = 500
# Позиция «играющего» звука не менялась дольше — считаем, что он завис.
CLOCK_STALL_MS = 1000

logger = logging.getLogger(__name__)


class CommandKind(Enum):
    SEEK = "seek"
    RATE = "rate"
    PAUSE = "pause"
    PLAY = "play"


@dataclass(frozen=True, slots=True)
class Command:
    kind: CommandKind
    value: float = 0.0

    @classmethod
    def seek(cls, position_ms: int) -> Command:
        return cls(CommandKind.SEEK, float(position_ms))

    @classmethod
    def rate(cls, rate: float) -> Command:
        return cls(CommandKind.RATE, rate)


PAUSE = Command(CommandKind.PAUSE)
PLAY = Command(CommandKind.PLAY)


@dataclass(frozen=True, slots=True)
class AudioState:
    position_ms: int
    playing: bool
    buffering: bool = False


@dataclass(frozen=True, slots=True)
class VideoState:
    position_ms: int
    duration_ms: int
    playing: bool
    buffering: bool = False
    seekable: bool = True

    @property
    def ready(self) -> bool:
        return self.seekable and self.duration_ms > 0


class AudioClock:
    """Сглаженная позиция звука между редкими обновлениями движка."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._now = clock
        self._raw: int | None = None
        self._raw_at = 0.0
        self._stalled = False

    @property
    def stalled(self) -> bool:
        """Движок говорит «играю», а позиция стоит: сеть или декодер."""
        return self._stalled

    def reset(self) -> None:
        self._raw = None
        self._stalled = False

    def read(self, position_ms: int, *, running: bool) -> int:
        position = max(0, int(position_ms))
        now = self._now()
        if not running or position != self._raw:
            self._raw = position
            self._raw_at = now
            self._stalled = False
            return position
        elapsed = max(0, int((now - self._raw_at) * 1000))
        self._stalled = elapsed > CLOCK_STALL_MS
        return position + min(elapsed, CLOCK_MAX_EXTRAPOLATION_MS)


@dataclass(slots=True)
class _PendingSeek:
    target_ms: int
    started_at: float


class WallpaperSync:
    """Решает, что сделать с видео, чтобы оно шло вровень со звуком."""

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._now = clock
        self._audio_clock = AudioClock(clock)
        self._active = False
        self._loop = False
        self._rate = 1.0
        self._lead_ms: float = float(INITIAL_SEEK_LEAD_MS)
        self._pending: _PendingSeek | None = None
        self._failed_seeks = 0
        self._seek_blocked_until = 0.0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def rate(self) -> float:
        return self._rate

    @property
    def lead_ms(self) -> int:
        return int(self._lead_ms)

    @property
    def seek_blocked(self) -> bool:
        return self._now() < self._seek_blocked_until

    def start(self, *, loop: bool = False) -> None:
        """Новое видео. Упреждение не сбрасываем: сеть та же."""
        self._active = True
        self._loop = loop
        self._rate = 1.0
        self._pending = None
        self._failed_seeks = 0
        self._seek_blocked_until = 0.0
        self._audio_clock.reset()

    def stop(self) -> None:
        self._active = False
        self._pending = None

    def audio_jumped(self) -> None:
        """Пользователь перемотал трек — старая перемотка видео уже не нужна."""
        self._pending = None
        self._seek_blocked_until = 0.0
        self._audio_clock.reset()

    def tick(self, audio: AudioState, video: VideoState) -> list[Command]:
        if not self._active:
            return []
        running = audio.playing and not audio.buffering
        audio_ms = self._audio_clock.read(audio.position_ms, running=running)
        if not running or self._audio_clock.stalled:
            return self._hold(video)
        if self._loop:
            return [] if video.playing else [PLAY]
        if not video.ready:
            return []

        if self._pending is not None:
            commands = self._settle(audio_ms, video)
            if self._pending is not None:
                return commands

        if audio_ms >= video.duration_ms - END_GUARD_MS:
            return self._hold(video)

        drift = audio_ms - video.position_ms
        ahead = -drift
        if SOFT_LIMIT_MS < ahead <= AHEAD_WAIT_MS:
            return self._hold(video)
        if not video.playing and DEADBAND_MS < ahead <= AHEAD_WAIT_MS:
            # Ждём на паузе, пока звук не догонит кадр.
            return []
        if (drift > SOFT_LIMIT_MS or ahead > AHEAD_WAIT_MS) and not self.seek_blocked:
            return self._seek(audio_ms, video)

        commands = self._retune(drift, buffering=video.buffering)
        if not video.playing:
            commands.append(PLAY)
        return commands

    def _hold(self, video: VideoState) -> list[Command]:
        commands = self._set_rate(1.0)
        if video.playing:
            commands.append(PAUSE)
        return commands

    def _seek(self, audio_ms: int, video: VideoState) -> list[Command]:
        target = min(
            audio_ms + int(self._lead_ms), video.duration_ms - END_GUARD_MS
        )
        target = max(0, target)
        self._pending = _PendingSeek(target_ms=target, started_at=self._now())
        logger.info(
            "Синхр. фона: перемотка видео %d → %d мс (звук %d, Δ=%+d, упреждение %d)",
            video.position_ms,
            target,
            audio_ms,
            audio_ms - video.position_ms,
            int(self._lead_ms),
        )
        commands = [Command.seek(target), *self._set_rate(1.0)]
        if not video.playing:
            commands.append(PLAY)
        return commands

    def _settle(self, audio_ms: int, video: VideoState) -> list[Command]:
        pending = self._pending
        assert pending is not None
        progressed = (
            video.playing
            and not video.buffering
            and video.position_ms >= pending.target_ms + SETTLE_PROGRESS_MS
        )
        took_s = self._now() - pending.started_at
        if not progressed and took_s < SETTLE_TIMEOUT_S:
            return [] if video.playing else [PLAY]
        self._pending = None
        took_ms = int(took_s * 1000)
        if not progressed:
            self._failed_seeks += 1
            backoff = min(
                SEEK_BACKOFF_MAX_S,
                SEEK_BACKOFF_BASE_S * 2 ** (self._failed_seeks - 1),
            )
            self._seek_blocked_until = self._now() + backoff
            logger.info(
                "Синхр. фона: видео не пошло за %d мс, следующая перемотка "
                "не раньше чем через %.0f с",
                took_ms,
                backoff,
            )
            return []
        self._failed_seeks = 0
        # > 0: видео всё ещё отстаёт — упреждения было мало.
        residual = audio_ms - video.position_ms
        if took_s <= LEAD_LEARN_MAX_SETTLE_S:
            step = max(
                -LEAD_LEARN_MAX_RESIDUAL_MS,
                min(LEAD_LEARN_MAX_RESIDUAL_MS, residual),
            )
            learned = self._lead_ms + step * LEAD_LEARN_RATE
            self._lead_ms = min(MAX_SEEK_LEAD_MS, max(0.0, learned))
        logger.info(
            "Синхр. фона: перемотка за %d мс, остаток Δ=%+d, упреждение → %d",
            took_ms,
            residual,
            int(self._lead_ms),
        )
        return []

    def _retune(self, drift_ms: int, *, buffering: bool) -> list[Command]:
        if buffering or abs(drift_ms) <= DEADBAND_MS:
            return self._set_rate(1.0)
        delta = drift_ms / CORRECTION_WINDOW_MS
        delta = max(-MAX_RATE_DELTA, min(MAX_RATE_DELTA, delta))
        return self._set_rate(round(1.0 + delta, 3))

    def _set_rate(self, rate: float) -> list[Command]:
        if rate == self._rate:
            return []
        if rate != 1.0 and abs(rate - self._rate) < RATE_STEP:
            return []
        self._rate = rate
        return [Command.rate(rate)]
