from __future__ import annotations

from quantis.services.wallpaper_policy import (
    WALLPAPER_CACHE_MAX_SEC,
    WALLPAPER_MAX_DRIFT_MS,
    WALLPAPER_SYNC_DRIFT_MS,
    clamp_wallpaper_fps,
    clamp_wallpaper_quality,
    should_fetch_wallpaper_now,
    should_play_local_wallpaper,
    wallpaper_cache_format,
    wallpaper_decode_max_side,
    wallpaper_duration_filter,
    wallpaper_next_drift_tolerance,
    wallpaper_positions_drifted,
    wallpaper_stream_conflicts,
    wallpaper_yt_dlp_format,
)


def test_remote_wallpaper_waits_for_audio() -> None:
    assert should_fetch_wallpaper_now(local=True, audio_live=False)
    assert should_fetch_wallpaper_now(local=False, audio_live=True)
    assert not should_fetch_wallpaper_now(local=False, audio_live=False)


def test_local_short_clip_is_used() -> None:
    assert should_play_local_wallpaper(5 * 1024 * 1024)
    assert not should_play_local_wallpaper(80 * 1024 * 1024)
    assert not should_play_local_wallpaper(0)


def test_yt_dlp_skips_long_video_cache() -> None:
    assert wallpaper_duration_filter({"duration": 240}) is None
    assert wallpaper_duration_filter({"duration": WALLPAPER_CACHE_MAX_SEC}) is None
    assert wallpaper_duration_filter({"duration": 3600}) is not None


def test_syncs_when_audio_and_video_drift() -> None:
    assert wallpaper_positions_drifted(60_000, 56_000)
    assert not wallpaper_positions_drifted(60_000, 59_000)
    assert not wallpaper_positions_drifted(0, 1000)
    assert not wallpaper_positions_drifted(10_000, 8_000, tolerance_ms=3_000)


def test_drift_tolerance_grows_then_caps() -> None:
    grown = wallpaper_next_drift_tolerance(WALLPAPER_SYNC_DRIFT_MS)
    assert grown == WALLPAPER_SYNC_DRIFT_MS * 2
    assert wallpaper_next_drift_tolerance(WALLPAPER_MAX_DRIFT_MS) == WALLPAPER_MAX_DRIFT_MS


def test_quality_and_fps_are_clamped_to_choices() -> None:
    assert clamp_wallpaper_quality(720) == 720
    assert clamp_wallpaper_quality(1080) == 720
    assert clamp_wallpaper_quality(400) == 360
    assert clamp_wallpaper_fps(30) == 30
    assert clamp_wallpaper_fps(12) == 10
    assert clamp_wallpaper_fps(60) == 30


def test_yt_dlp_format_includes_requested_height() -> None:
    assert "height<=360" in wallpaper_cache_format(360)
    assert "height<=720" in wallpaper_cache_format(720)
    assert wallpaper_decode_max_side(720) > wallpaper_decode_max_side(360)


def test_wallpaper_stream_prefers_video_only() -> None:
    fmt = wallpaper_yt_dlp_format(360)
    assert fmt.startswith("bestvideo")
    assert "acodec=none" in fmt


def test_wallpaper_stream_conflicts_on_same_itag() -> None:
    audio = "https://rr1.googlevideo.com/videoplayback?id=abc&itag=18&range=0-1"
    video = "https://rr1.googlevideo.com/videoplayback?id=abc&itag=18&range=2-9"
    other = "https://rr1.googlevideo.com/videoplayback?id=abc&itag=134"
    assert wallpaper_stream_conflicts(audio, video)
    assert not wallpaper_stream_conflicts(audio, other)
    assert wallpaper_stream_conflicts(audio, audio)
    assert not wallpaper_stream_conflicts("http://127.0.0.1:9/p", video)
