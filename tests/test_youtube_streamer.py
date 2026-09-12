"""Тесты выбора формата YouTube."""

from __future__ import annotations

from quantis.services.youtube_streamer import AsyncYoutubeStreamer


def test_rejects_hls_and_dash_formats() -> None:
    assert not AsyncYoutubeStreamer._is_playable_format(
        {"url": "http://x", "protocol": "m3u8_native"}
    )
    assert not AsyncYoutubeStreamer._is_playable_format(
        {"url": "http://x", "protocol": "http_dash_segments"}
    )


def test_accepts_https_progressive() -> None:
    assert AsyncYoutubeStreamer._is_playable_format(
        {"url": "https://rr.example/videoplayback", "protocol": "https", "ext": "m4a"}
    )


def test_picks_audio_only_over_muxed_video() -> None:
    info = {
        "url": "https://rr.example/video.mp4",
        "protocol": "https",
        "ext": "mp4",
        "vcodec": "h264",
        "acodec": "aac",
        "formats": [
            {
                "url": "https://rr.example/video.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "aac",
                "tbr": 200,
            },
            {
                "url": "https://rr.example/audio.m4a",
                "protocol": "https",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "aac",
                "abr": 128,
            },
        ],
    }
    assert (
        AsyncYoutubeStreamer._pick_stream_url(info, prefer_video=False)
        == "https://rr.example/audio.m4a"
    )


def test_duration_from_info_seconds() -> None:
    assert AsyncYoutubeStreamer._duration_ms_from_info({"duration": 201}) == 201_000
    assert AsyncYoutubeStreamer._duration_ms_from_info({}) == 0
    assert AsyncYoutubeStreamer._duration_ms_from_info(None) == 0


def test_audio_attempts_use_socket_timeout() -> None:
    streamer = AsyncYoutubeStreamer(None)  # type: ignore[arg-type]
    attempts = streamer._attempt_opts(video=False)
    assert attempts
    assert all(opts.get("socket_timeout") == 8 for opts in attempts)
    first_clients = (
        (attempts[0].get("extractor_args") or {})
        .get("youtube", {})
        .get("player_client")
    )
    assert first_clients == ["android", "web"]


def test_wallpaper_video_format_is_360p() -> None:
    streamer = AsyncYoutubeStreamer(None)  # type: ignore[arg-type]
    video_opts = streamer._attempt_opts(video=True)
    for opts in video_opts:
        fmt = opts["format"]
        assert "height<=720" not in fmt
        assert "height<=360" in fmt or fmt.startswith("18/")


def test_wallpaper_video_format_honors_720p() -> None:
    streamer = AsyncYoutubeStreamer(None)  # type: ignore[arg-type]
    video_opts = streamer._attempt_opts(video=True, height=720)
    for opts in video_opts:
        assert "height<=720" in opts["format"] or opts["format"].startswith("18/")


def test_picks_video_near_requested_height() -> None:
    info = {
        "formats": [
            {
                "url": "https://rr.example/360.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "aac",
                "height": 360,
                "tbr": 400,
            },
            {
                "url": "https://rr.example/720.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "aac",
                "height": 720,
                "tbr": 1500,
            },
        ],
    }
    assert (
        AsyncYoutubeStreamer._pick_stream_url(
            info, prefer_video=True, target_height=360
        )
        == "https://rr.example/360.mp4"
    )
    assert (
        AsyncYoutubeStreamer._pick_stream_url(
            info, prefer_video=True, target_height=720
        )
        == "https://rr.example/720.mp4"
    )

