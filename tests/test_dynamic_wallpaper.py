"""Контроллер видео-фона: не перезагружает поток по кругу."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Signal  # noqa: E402

from quantis.plugins.event_bus import EventBus  # noqa: E402
from quantis.services.wallpaper_sync import VideoState  # noqa: E402
from quantis.ui.controllers import dynamic_wallpaper  # noqa: E402
from quantis.ui.controllers.dynamic_wallpaper import (  # noqa: E402
    DynamicWallpaperController,
)


class _Prefs(QObject):
    changed = Signal()
    dynamic_wallpaper_enabled = True
    dynamic_wallpaper_quality = 360
    dynamic_wallpaper_fps = 10
    dynamic_wallpaper_av_delay_ms = 250


class _Player:
    time = 42_000
    duration = 240_000
    current_source = "http://127.0.0.1:1/audio"
    media_player = None

    def is_playing(self) -> bool:
        return True

    def is_buffering(self) -> bool:
        return False

    def on_source_changed(self, _callback) -> None:
        pass


class _Playback:
    audio_live = True
    player = _Player()


class _Bridge:
    def __init__(self) -> None:
        self.scheduled: list[str] = []

    def invoke_main(self, fn) -> None:
        fn()

    def schedule(self, coro) -> None:
        self.scheduled.append(coro.__qualname__)
        coro.close()


class _Backdrop(QObject):
    stream_stalled = Signal()
    media_ready = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.url = "https://rr1.googlevideo.com/videoplayback?id=a&itag=137"

    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    def is_video_playing(self) -> bool:
        return False  # поток упал — как в логе с битым itag 137

    def is_following_audio_player(self) -> bool:
        return False

    def video_state(self):
        return None

    def current_video_url(self) -> str:
        return self.url


class _Track:
    source = "youtube"
    track_id = "nSQtqPRi3wI"


@pytest.fixture
def controller(qapp, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        DynamicWallpaperController, "_existing_cover_path", staticmethod(lambda t: None)
    )
    monkeypatch.setattr(
        DynamicWallpaperController, "_local_video_path", lambda self, t: None
    )
    bridge = _Bridge()
    ctrl = DynamicWallpaperController(
        _Backdrop(),
        music=None,
        bridge=bridge,
        preferences=_Prefs(),
        event_bus=EventBus(),
        playback=_Playback(),
    )
    return ctrl, bridge


def test_repeated_track_events_do_not_reload_video(controller) -> None:
    ctrl, bridge = controller
    track = _Track()
    for _ in range(50):
        ctrl._on_track_changed(track)
        ctrl.refresh_for_track(track)
    loads = [name for name in bridge.scheduled if "load_video" in name]
    assert len(loads) == 1


def test_quality_change_forces_reload(controller) -> None:
    ctrl, bridge = controller
    track = _Track()
    ctrl._on_track_changed(track)
    ctrl._loading_key = None  # первая загрузка завершилась
    ctrl._on_track_changed(track, force=True)
    loads = [name for name in bridge.scheduled if "load_video" in name]
    assert len(loads) == 2


def test_stalling_format_is_excluded_then_cover(
    controller, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctrl, bridge = controller
    ctrl._on_track_changed(_Track())
    clock = [1000.0]
    monkeypatch.setattr(dynamic_wallpaper, "monotonic", lambda: clock[0])
    for _ in range(4):
        ctrl._on_stream_stalled()
        clock[0] += 5
    assert "137" in ctrl._excluded_itags
    assert bridge.scheduled.count("DynamicWallpaperController._reload_video") == 4
    ctrl._on_stream_stalled()
    assert bridge.scheduled[-1] == "DynamicWallpaperController._show_cover"


def test_video_follows_heard_audio_not_decoder(controller) -> None:
    """Видео держится позади позиции плеера на задержку аудиовыхода."""
    ctrl, _bridge = controller
    seen = []
    ctrl._sync.start()
    ctrl._sync.tick = lambda audio, video: seen.append(audio.position_ms) or []
    state = VideoState(position_ms=41_750, duration_ms=240_000, playing=True)
    ctrl._backdrop.video_state = lambda: state
    ctrl._tick()
    assert seen == [_Player.time - 250]


def test_stall_burst_is_rate_limited(controller, monkeypatch) -> None:
    ctrl, bridge = controller
    ctrl._on_track_changed(_Track())
    monkeypatch.setattr(dynamic_wallpaper, "monotonic", lambda: 1000.0)
    for _ in range(20):
        ctrl._on_stream_stalled()
    assert bridge.scheduled.count("DynamicWallpaperController._reload_video") == 1
