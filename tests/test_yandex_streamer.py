"""Длина трека берётся из каталога Яндекса при получении ссылки."""

from __future__ import annotations

import sys
import types

from quantis.models import YandexTrack
from quantis.services.yandex_streamer import AsyncYandexStreamer


class _Info:
    preview = False
    codec = "mp3"
    bitrate_in_kbps = 320

    def get_direct_link(self) -> str:
        return "https://cdn/track.mp3"


class _CatalogTrack:
    duration_ms = 238_000

    def get_download_info(self):
        return [_Info()]


class _Client:
    def __init__(self, token: str) -> None:
        pass

    def tracks(self, track_id: int):
        return [_CatalogTrack()]


def test_stream_url_refreshes_duration_from_catalog(monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules, "yandex_music", types.SimpleNamespace(Client=_Client)
    )
    streamer = AsyncYandexStreamer(executor=None)  # type: ignore[arg-type]
    monkeypatch.setattr(streamer, "_yandex_token", lambda: "token")
    # Длина, «прилипшая» от прошлого трека и сохранённая в истории.
    track = YandexTrack(
        track_id="1", title="Creep", author="Radiohead", duration_ms=187_872
    )

    assert streamer._sync_get_stream_url(track) == "https://cdn/track.mp3"
    assert track.duration_ms == 238_000
