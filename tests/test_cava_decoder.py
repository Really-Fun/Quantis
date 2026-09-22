from __future__ import annotations

import sys
from array import array
from pathlib import Path

import pytest

_PLUGIN = Path(__file__).resolve().parents[1] / "plugins_dir" / "cava"
# plugins_dir не в git: плагины живут у разработчика локально.
if not _PLUGIN.is_dir():
    pytest.skip("нет plugins_dir/cava", allow_module_level=True)
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

from decoder import SAMPLE_RATE, PcmCache, is_http_source  # noqa: E402


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


def test_pcm_cache_trims_old_samples(qapp) -> None:
    cache = PcmCache()
    cache._samples = array("h", [1] * (SAMPLE_RATE * 60))
    cache._origin = 0
    cache.set_position(50_000)
    assert cache._origin > 0
    assert len(cache._samples) <= SAMPLE_RATE * 40
    window = cache.window(50_000, 1024)
    assert window is not None
    assert len(window) == 1024
    cache.clear()
