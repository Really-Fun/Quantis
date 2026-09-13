"""Тесты выбора формата YouTube."""

from __future__ import annotations

from quantis.services.youtube_streamer import AsyncYoutubeStreamer, slim_youtube_info


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


_INFO = {
    "duration": 201,
    "formats": [
        {
            "url": "https://rr.example/audio.m4a",
            "protocol": "https",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "aac",
            "abr": 128,
        },
        {
            "url": "https://rr.example/video-only.mp4",
            "protocol": "https",
            "ext": "mp4",
            "vcodec": "h264",
            "acodec": "none",
            "height": 360,
            "tbr": 250,
        },
    ],
}


def test_slim_info_drops_heavy_fields() -> None:
    fat = {
        **_INFO,
        "description": "x" * 4000,
        "thumbnails": [{"url": "http://x"}] * 40,
        "automatic_captions": {"en": [{"url": "http://c"}]},
        "heatmap": list(range(200)),
        "formats": [
            *_INFO["formats"],
            {"url": "", "protocol": "https", "ext": "m4a"},
        ],
    }
    slim = slim_youtube_info(fat)
    assert slim is not None
    assert "description" not in slim
    assert "thumbnails" not in slim
    assert "automatic_captions" not in slim
    assert "heatmap" not in slim
    assert slim["duration"] == 201
    assert all(fmt.get("url") for fmt in slim["formats"])

    streamer = AsyncYoutubeStreamer(None)  # type: ignore[arg-type]
    streamer._store_info("dQw4w9WgXcQ", fat)
    cached = streamer._cached_info("dQw4w9WgXcQ")
    assert cached is not None
    assert "thumbnails" not in cached
    assert cached["formats"]


def test_video_reuses_cached_audio_extract() -> None:
    streamer = AsyncYoutubeStreamer(None)  # type: ignore[arg-type]
    streamer._store_info("dQw4w9WgXcQ", _INFO)
    audio, duration = streamer.sync_stream("dQw4w9WgXcQ")
    video, video_duration = streamer.sync_video_stream("dQw4w9WgXcQ", 360)
    assert audio == "https://rr.example/audio.m4a"
    assert video == "https://rr.example/video-only.mp4"
    assert duration == 201_000
    assert video_duration == 201


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
    first_youtube = (attempts[0].get("extractor_args") or {}).get("youtube", {})
    assert first_youtube.get("player_client") == ["android"]
    assert "webpage" in (first_youtube.get("player_skip") or [])
    assert "web" not in first_youtube.get("player_client", [])
    second_clients = (
        (attempts[1].get("extractor_args") or {})
        .get("youtube", {})
        .get("player_client")
    )
    assert "web" in second_clients


def test_wallpaper_video_format_is_360p() -> None:
    streamer = AsyncYoutubeStreamer(None)  # type: ignore[arg-type]
    video_opts = streamer._attempt_opts(video=True)
    for opts in video_opts:
        fmt = opts["format"]
        assert "bestvideo" in fmt
        assert "acodec=none" in fmt
        assert "height<=360" in fmt


def test_wallpaper_video_format_honors_720p() -> None:
    streamer = AsyncYoutubeStreamer(None)  # type: ignore[arg-type]
    video_opts = streamer._attempt_opts(video=True, height=720)
    for opts in video_opts:
        assert "height<=720" in opts["format"] or opts["format"].startswith("18/")


def test_picks_video_only_over_muxed() -> None:
    info = {
        "url": "https://rr.example/muxed.mp4",
        "protocol": "https",
        "ext": "mp4",
        "vcodec": "h264",
        "acodec": "aac",
        "height": 360,
        "formats": [
            {
                "url": "https://rr.example/muxed.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "aac",
                "height": 360,
                "tbr": 400,
            },
            {
                "url": "https://rr.example/video-only.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "none",
                "height": 360,
                "tbr": 250,
            },
        ],
    }
    picked = AsyncYoutubeStreamer._pick_stream_url(
        info, prefer_video=True, target_height=360
    )
    assert picked == "https://rr.example/video-only.mp4"


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

