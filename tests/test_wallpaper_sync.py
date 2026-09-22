"""Ядро синхронизации видео-фона: команды и сходимость на модели плеера."""

from __future__ import annotations

from dataclasses import dataclass

from quantis.services.wallpaper_sync import (
    CLOCK_STALL_MS,
    DEADBAND_MS,
    END_GUARD_MS,
    INITIAL_SEEK_LEAD_MS,
    MAX_RATE_DELTA,
    SEEK_BACKOFF_BASE_S,
    SETTLE_TIMEOUT_S,
    SOFT_LIMIT_MS,
    SYNC_TICK_MS,
    AudioClock,
    AudioState,
    Command,
    CommandKind,
    VideoState,
    WallpaperSync,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance_ms(self, ms: float) -> None:
        self.now += ms / 1000


def _video(
    position_ms: int = 0,
    *,
    duration_ms: int = 240_000,
    playing: bool = True,
    buffering: bool = False,
) -> VideoState:
    return VideoState(
        position_ms=position_ms,
        duration_ms=duration_ms,
        playing=playing,
        buffering=buffering,
    )


def _kinds(commands: list[Command]) -> list[CommandKind]:
    return [command.kind for command in commands]


def test_inactive_core_does_nothing() -> None:
    sync = WallpaperSync(FakeClock())
    assert sync.tick(AudioState(10_000, True), _video(0)) == []


def test_audio_pause_pauses_video() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    commands = sync.tick(AudioState(10_000, playing=False), _video(10_000))
    assert _kinds(commands) == [CommandKind.PAUSE]
    # Уже стоит — повторно не дёргаем
    assert sync.tick(AudioState(10_000, False), _video(10_000, playing=False)) == []


def test_audio_buffering_holds_video() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    audio = AudioState(10_000, playing=True, buffering=True)
    assert _kinds(sync.tick(audio, _video(10_000))) == [CommandKind.PAUSE]


def test_waits_until_video_is_seekable() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    video = _video(0, duration_ms=0, playing=False)
    assert sync.tick(AudioState(30_000, True), video) == []


def test_first_frame_is_seeked_to_audio_with_lead() -> None:
    """Видео ждёт на паузе и стартует уже на позиции трека."""
    sync = WallpaperSync(FakeClock())
    sync.start()
    commands = sync.tick(AudioState(30_000, True), _video(0, playing=False))
    assert commands[0] == Command.seek(30_000 + INITIAL_SEEK_LEAD_MS)
    assert commands[-1].kind is CommandKind.PLAY


def test_small_paused_gap_just_plays() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    commands = sync.tick(AudioState(10_000, True), _video(9_980, playing=False))
    assert _kinds(commands) == [CommandKind.PLAY]


def test_small_drift_is_fixed_by_rate_not_seek() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    behind = sync.tick(AudioState(10_000, True), _video(9_700))
    assert _kinds(behind) == [CommandKind.RATE]
    assert behind[0].value > 1.0
    ahead = sync.tick(AudioState(10_000, True), _video(10_300))
    assert ahead[0].value < 1.0


def test_rate_is_capped_and_resets_inside_deadband() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    sync.tick(AudioState(10_000, True), _video(10_000 - SOFT_LIMIT_MS + 10))
    assert sync.rate == 1.0 + MAX_RATE_DELTA
    back = sync.tick(AudioState(10_000, True), _video(10_000 - DEADBAND_MS // 2))
    assert back == [Command.rate(1.0)]


def test_video_buffering_does_not_speed_up() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    assert sync.tick(AudioState(10_000, True), _video(9_500, buffering=True)) == []
    assert sync.rate == 1.0


def test_large_drift_seeks_and_waits_for_settle() -> None:
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    commands = sync.tick(AudioState(60_000, True), _video(50_000))
    assert commands == [Command.seek(60_000 + INITIAL_SEEK_LEAD_MS)]
    # Пока видео не ушло вперёд от цели — новых команд нет
    clock.advance_ms(200)
    assert sync.tick(AudioState(60_200, True), _video(60_300, buffering=True)) == []


def test_seek_lead_learns_from_residual() -> None:
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    sync.tick(AudioState(60_000, True), _video(0))
    target = 60_000 + INITIAL_SEEK_LEAD_MS
    # Декодер буферизовался секунду: видео на цели+200, звук ушёл дальше
    clock.advance_ms(1_200)
    sync.tick(AudioState(61_200, True), _video(target + 200))
    assert sync.lead_ms > INITIAL_SEEK_LEAD_MS


def test_failed_seek_backs_off_instead_of_hammering_cdn() -> None:
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    sync.tick(AudioState(60_000, True), _video(0))
    clock.advance_ms(SETTLE_TIMEOUT_S * 1000 + 1)
    lead = sync.lead_ms
    # Перемотки нет: пока пауза, догоняем максимальной скоростью
    assert sync.tick(AudioState(65_000, True), _video(20_000)) == [
        Command.rate(1.0 + MAX_RATE_DELTA)
    ]
    assert sync.seek_blocked
    assert sync.lead_ms == lead
    # Пауза кончилась — пробуем снова
    clock.advance_ms(SEEK_BACKOFF_BASE_S * 1000 + 1)
    commands = sync.tick(AudioState(67_000, True), _video(22_000))
    assert commands[0].kind is CommandKind.SEEK


def test_backoff_grows_with_each_failure() -> None:
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    waits = []

    def audio() -> AudioState:
        return AudioState(60_000 + int(clock.now * 1000), True)

    for _ in range(3):
        sync.tick(audio(), _video(0))
        clock.advance_ms(SETTLE_TIMEOUT_S * 1000 + 1)
        sync.tick(audio(), _video(0))
        blocked_for = 0.0
        while sync.seek_blocked:
            clock.advance_ms(500)
            blocked_for += 0.5
        waits.append(blocked_for)
    assert waits[0] < waits[1] < waits[2]


def test_slow_settle_does_not_teach_lead() -> None:
    """Перемотка за 5 с на забитом канале — не задержка декодера."""
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    sync.tick(AudioState(60_000, True), _video(0))
    target = 60_000 + INITIAL_SEEK_LEAD_MS
    clock.advance_ms(4_500)
    sync.tick(AudioState(64_500, True), _video(target + 200))
    assert sync.lead_ms == INITIAL_SEEK_LEAD_MS


def test_video_ahead_waits_on_pause_instead_of_seeking_back() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    commands = sync.tick(AudioState(50_000, True), _video(52_500))
    assert _kinds(commands) == [CommandKind.PAUSE]
    # Пока звук не догнал — стоим
    assert sync.tick(AudioState(52_000, True), _video(52_500, playing=False)) == []
    # Догнал — поехали
    commands = sync.tick(AudioState(52_480, True), _video(52_500, playing=False))
    assert _kinds(commands) == [CommandKind.PLAY]


def test_frozen_audio_holds_video() -> None:
    """Звук «играет», но позиция стоит (сеть) — видео не убегает вперёд."""
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    sync.tick(AudioState(50_000, True), _video(50_000))
    clock.advance_ms(CLOCK_STALL_MS + 200)
    commands = sync.tick(AudioState(50_000, True), _video(51_200))
    assert _kinds(commands) == [CommandKind.PAUSE]
    # Звук ожил — видео продолжает
    clock.advance_ms(200)
    commands = sync.tick(AudioState(51_200, True), _video(51_200, playing=False))
    assert _kinds(commands) == [CommandKind.PLAY]


def test_user_seek_cancels_pending_video_seek() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    sync.tick(AudioState(60_000, True), _video(0))
    sync.audio_jumped()
    commands = sync.tick(AudioState(5_000, True), _video(60_300))
    assert commands[0] == Command.seek(5_000 + INITIAL_SEEK_LEAD_MS)


def test_clip_shorter_than_track_freezes_on_last_frame() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start()
    video = _video(118_000, duration_ms=120_000)
    assert _kinds(sync.tick(AudioState(150_000, True), video)) == [CommandKind.PAUSE]
    # Возврат звука в пределы клипа — видео снова идёт
    commands = sync.tick(
        AudioState(60_000, True), _video(120_000 - END_GUARD_MS, playing=False)
    )
    assert commands[0].kind is CommandKind.SEEK


def test_loop_clip_only_follows_play_state() -> None:
    sync = WallpaperSync(FakeClock())
    sync.start(loop=True)
    assert sync.tick(AudioState(90_000, True), _video(3_000)) == []
    stopped = _video(3_000, playing=False)
    assert _kinds(sync.tick(AudioState(90_000, True), stopped)) == [CommandKind.PLAY]
    assert _kinds(sync.tick(AudioState(90_000, False), _video(3_000))) == [
        CommandKind.PAUSE
    ]


def test_audio_clock_extrapolates_between_coarse_updates() -> None:
    clock = FakeClock()
    audio = AudioClock(clock)
    assert audio.read(10_000, running=True) == 10_000
    clock.advance_ms(200)
    assert audio.read(10_000, running=True) == 10_200
    clock.advance_ms(2_000)
    assert audio.read(10_000, running=True) == 10_500
    assert audio.read(10_000, running=False) == 10_000
    assert audio.read(12_000, running=True) == 12_000


@dataclass
class _SimVideo:
    """Модель QMediaPlayer на HTTP: после перемотки декодер буферизуется."""

    seek_latency_ms: int
    position: float = 0.0
    playing: bool = False
    rate: float = 1.0
    buffering_left_ms: float = 0.0
    duration_ms: int = 600_000

    def apply(self, command: Command) -> None:
        if command.kind is CommandKind.SEEK:
            self.position = command.value
            self.buffering_left_ms = self.seek_latency_ms
        elif command.kind is CommandKind.RATE:
            self.rate = command.value
        elif command.kind is CommandKind.PAUSE:
            self.playing = False
        elif command.kind is CommandKind.PLAY:
            self.playing = True

    def advance(self, ms: float) -> None:
        if not self.playing:
            return
        if self.buffering_left_ms > 0:
            self.buffering_left_ms -= ms
            return
        self.position += ms * self.rate

    def state(self) -> VideoState:
        return VideoState(
            position_ms=int(self.position),
            duration_ms=self.duration_ms,
            playing=self.playing,
            buffering=self.buffering_left_ms > 0,
        )


def _simulate(
    sync: WallpaperSync,
    clock: FakeClock,
    video: _SimVideo,
    *,
    audio_start: float,
    seconds: float,
    drift_ppm: float = 0.0,
) -> float:
    audio = audio_start
    for _ in range(int(seconds * 1000 / SYNC_TICK_MS)):
        for command in sync.tick(AudioState(int(audio), True), video.state()):
            video.apply(command)
        clock.advance_ms(SYNC_TICK_MS)
        audio += SYNC_TICK_MS
        video.advance(SYNC_TICK_MS * (1 + drift_ppm / 1e6))
    return audio


def test_converges_to_tight_sync_despite_seek_latency() -> None:
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    video = _SimVideo(seek_latency_ms=700)
    audio = _simulate(sync, clock, video, audio_start=42_000, seconds=30)
    assert abs(audio - video.position) <= DEADBAND_MS * 2
    # Упреждение выучило задержку CDN
    assert 400 <= sync.lead_ms <= 1_000


def test_holds_sync_against_clock_drift_without_seeking() -> None:
    """Часы видео спешат на 2 % — поправляет скорость, не перемотка."""
    clock = FakeClock()
    sync = WallpaperSync(clock)
    sync.start()
    video = _SimVideo(seek_latency_ms=0)
    _simulate(sync, clock, video, audio_start=10_000, seconds=5)

    seeks = 0
    original_apply = video.apply

    def counting_apply(command: Command) -> None:
        nonlocal seeks
        seeks += command.kind is CommandKind.SEEK
        original_apply(command)

    video.apply = counting_apply  # type: ignore[method-assign]
    audio = _simulate(
        sync, clock, video, audio_start=10_000 + 5_000, seconds=60, drift_ppm=20_000
    )
    assert seeks == 0
    assert abs(audio - video.position) <= 150
