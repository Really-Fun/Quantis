from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from quantis.models import Track, TrackSource
from quantis.services import net_proxy
from quantis.services.net_proxy import (
    is_youtube_url,
    normalize_proxy,
    proxy_label,
    requests_proxies,
    set_youtube_proxy,
    with_youtube_proxy,
    ytdlp_proxy,
)


@pytest.fixture(autouse=True)
def _no_proxy_after():
    yield
    set_youtube_proxy("")


def test_normalize_accepts_common_spellings() -> None:
    assert normalize_proxy("") == ""
    assert normalize_proxy("  127.0.0.1:8080 ") == "http://127.0.0.1:8080"
    assert normalize_proxy("SOCKS5://127.0.0.1:1080") == "socks5://127.0.0.1:1080"
    assert normalize_proxy("socks5://u:p@host:1") == "socks5://u:p@host:1"


@pytest.mark.parametrize(
    "text", ["ftp://host:1", "socks5://127.0.0.1", "http://:8080", "host:port"]
)
def test_normalize_rejects_bad_addresses(text: str) -> None:
    with pytest.raises(ValueError):
        normalize_proxy(text)


def test_proxy_reaches_ytdlp_and_requests_with_remote_dns() -> None:
    opts = {"quiet": True}
    assert with_youtube_proxy(opts) is opts and requests_proxies() is None
    set_youtube_proxy("socks5://u:secret@127.0.0.1:1080")
    # имена разрешает прокси: местный DNS для YouTube может быть подменён
    assert ytdlp_proxy() == "socks5h://u:secret@127.0.0.1:1080"
    assert with_youtube_proxy(opts)["proxy"] == ytdlp_proxy()
    assert "proxy" not in opts
    assert requests_proxies() == {"http": ytdlp_proxy(), "https": ytdlp_proxy()}
    assert proxy_label() == "socks5://127.0.0.1:1080"  # без логина и пароля


def test_bad_proxy_is_ignored_and_listeners_hear_changes() -> None:
    calls: list[str] = []
    listener = lambda: calls.append(net_proxy.youtube_proxy())  # noqa: E731
    net_proxy.on_proxy_changed(listener)
    try:
        set_youtube_proxy("http://127.0.0.1:8080")
        set_youtube_proxy("http://127.0.0.1:8080")  # то же самое — тишина
        set_youtube_proxy("ftp://nope")
    finally:
        net_proxy._listeners.remove(listener)
    assert calls == ["http://127.0.0.1:8080", ""]


def test_youtube_hosts() -> None:
    assert is_youtube_url("https://rr3---sn-x.googlevideo.com/videoplayback?x=1")
    assert is_youtube_url("https://img.youtube.com/vi/abc/hqdefault.jpg")
    assert not is_youtube_url("https://evil.example/googlevideo.com")
    assert not is_youtube_url("https://storage.yandex.net/get-mp3/1")
    assert not is_youtube_url(None)


@pytest.mark.asyncio
async def test_aiohttp_connector_follows_proxy() -> None:
    assert net_proxy.aiohttp_connector() is None
    set_youtube_proxy("socks5h://127.0.0.1:1080")
    connector = net_proxy.aiohttp_connector()
    assert type(connector).__name__ == "ProxyConnector"
    await connector.close()


@pytest.mark.asyncio
async def test_youtube_playback_goes_through_local_proxy_only_with_proxy() -> None:
    from quantis.services.async_streamer import AsyncStreamer

    streamer = AsyncStreamer(ThreadPoolExecutor(max_workers=1))
    track = Track("dQw4w9WgXcQ", "Song", "Artist", source=TrackSource.YOUTUBE)
    direct = "https://rr1---sn-a.googlevideo.com/videoplayback?id=1"

    async def fake_url(_track):
        return direct

    streamer._youtube.get_stream_url = fake_url  # type: ignore[method-assign]
    try:
        assert await streamer.open_playback(track) == direct
        set_youtube_proxy("http://127.0.0.1:8080")  # и кэш ссылок сброшен
        local = await streamer.open_playback(track)
        assert local is not None and local.startswith("http://127.0.0.1:")
    finally:
        await streamer._http_proxy.close()


def test_failure_hint_names_the_cause() -> None:
    from quantis.services.async_streamer import AsyncStreamer

    streamer = AsyncStreamer(ThreadPoolExecutor(max_workers=1))
    track = Track("dQw4w9WgXcQ", "Song", "Artist", source=TrackSource.YOUTUBE)
    assert streamer.failure_hint(track) is None  # сеть ни при чём
    streamer._youtube._network_failed.add("dQw4w9WgXcQ")
    assert "недоступен в вашей сети" in streamer.failure_hint(track)
    assert "замедлен" in streamer.failure_hint(track, stalled=True)
    set_youtube_proxy("socks5://u:secret@127.0.0.1:1080")
    hint = streamer.failure_hint(track)
    assert "через прокси socks5://127.0.0.1:1080" in hint and "secret" not in hint
    yandex = Track(1, "Song", "Artist", source=TrackSource.YANDEX)
    assert streamer.failure_hint(yandex, stalled=True) is None


def test_blocked_youtube_counts_as_network_error() -> None:
    import ssl

    from yt_dlp.networking.exceptions import SSLError, TransportError
    from yt_dlp.utils import DownloadError

    from quantis.services.youtube_streamer import _is_network_error

    assert _is_network_error(SSLError("EOF"))
    assert _is_network_error(ssl.SSLError("handshake"))
    wrapped = DownloadError("x", exc_info=(TransportError, TransportError("r"), None))
    assert _is_network_error(wrapped)
    assert not _is_network_error(ValueError("no formats"))
