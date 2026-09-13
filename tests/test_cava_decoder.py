from __future__ import annotations

import sys
from pathlib import Path

_PLUGIN = Path(__file__).resolve().parents[1] / "plugins_dir" / "cava"
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

from decoder import PcmCache, is_http_source  # noqa: E402


def test_is_http_source() -> None:
    assert is_http_source(None) is False
    assert is_http_source("") is False
    assert is_http_source("/tmp/track.mp3") is False
    assert is_http_source("http://127.0.0.1:8765/yandex/1") is True
    assert is_http_source("https://googlevideo.com/videoplayback") is True


def test_pcm_cache_skips_http(qapp) -> None:
    cache = PcmCache()
    cache.load("http://127.0.0.1:1/yandex/1")
    assert cache._path is None
    assert cache.frames == 0
    cache.clear()
