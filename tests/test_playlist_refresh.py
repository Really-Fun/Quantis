"""Добавленный в плейлист трек виден сразу, без перезапуска."""

from __future__ import annotations

import asyncio

from quantis.models import UserPlaylist, YandexTrack
from quantis.plugins.event_bus import EventBus
from quantis.ui import playlist_actions
from quantis.ui.viewmodels.home_vm import (
    HomeSnapshot,
    _CountedShell,
    _with_user_playlists,
)


class InlineBridge:
    def schedule(self, coro) -> None:
        asyncio.run(coro)

    def invoke_main(self, fn) -> None:
        fn()


def _snapshot(*playlists) -> HomeSnapshot:
    return HomeSnapshot(
        greeting="",
        quick_playlists=tuple(playlists[:6]),
        library_playlists=tuple(playlists),
        recommendation_tracks=(),
        recent_tracks=(),
    )


def test_with_user_playlists_replaces_only_user_ones() -> None:
    liked = _CountedShell("Любимые", count=3, cover_path=None, kind="liked")
    old = UserPlaylist("Мой микс", (), None)
    track = YandexTrack(track_id="1", title="T", author="A")
    new = UserPlaylist("Мой микс", (track,), None)

    snap = _with_user_playlists(_snapshot(liked, old), [new])

    assert snap.library_playlists == (liked, new)
    assert snap.quick_playlists == (liked, new)
    assert len(snap.library_playlists[1]) == 1


def test_add_from_any_page_announces_playlists_updated(monkeypatch) -> None:
    bus = EventBus()
    seen: list[bool] = []
    bus.playlists_updated.connect(lambda: seen.append(True))
    monkeypatch.setattr(playlist_actions, "_event_bus", bus)

    class FakeService:
        async def add_track(self, name, track) -> bool:
            return True

    monkeypatch.setattr(playlist_actions, "UserPlaylistsService", FakeService)
    track = YandexTrack(track_id="1", title="T", author="A")
    bridge = InlineBridge()

    # Без on_done — как из библиотеки и со страницы плейлиста.
    bridge.schedule(
        playlist_actions.add_track_to_named("Мой микс", track, bridge, None, None)
    )

    assert seen == [True]
