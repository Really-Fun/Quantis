"""Порядок строк плейлиста управляет порядком воспроизведения."""

from __future__ import annotations

import asyncio

from PySide6.QtWidgets import QPushButton

from quantis.models import UserPlaylist, YandexTrack
from quantis.models.playlist import RecommendationPlaylist
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.viewmodels.playlist_vm import PlaylistViewModel
from quantis.ui.views.playlist_page import PlaylistPage


class PlaylistManagerStub:
    def __init__(self) -> None:
        self.current_playlist = None

    def set_playlist(self, playlist) -> None:
        self.current_playlist = playlist


class PlaybackStub:
    def __init__(self) -> None:
        self.playlist_manager = PlaylistManagerStub()
        self.played = []

    async def play_track(self, track) -> None:
        self.played.append(track)


def _tracks():
    return [
        YandexTrack("1", "Зима", "Борис", duration_ms=180_000),
        YandexTrack("2", "alpha", "анна", duration_ms=240_000),
        YandexTrack("3", "Ёж", "Анна", duration_ms=0),
    ]


def test_sorting_changes_visible_order_without_mutating_source(qapp) -> None:
    tracks = _tracks()
    playlist = UserPlaylist("Мой", tracks)
    vm = PlaylistViewModel(PlaybackStub())
    vm.set_playlist(playlist)

    vm.set_sort_order("artist_asc")
    assert [t.track_id for t in vm.model.all_tracks()] == ["2", "3", "1"]
    vm.set_sort_order("duration_desc")
    assert [t.track_id for t in vm.model.all_tracks()] == ["2", "1", "3"]
    vm.set_sort_order("duration_asc")
    assert [t.track_id for t in vm.model.all_tracks()] == ["1", "2", "3"]
    vm.set_sort_order("title_desc")
    assert [t.track_id for t in vm.model.all_tracks()] == ["1", "3", "2"]
    vm.set_sort_order("original")
    assert [t.track_id for t in vm.model.all_tracks()] == ["1", "2", "3"]
    assert list(playlist.tracks.values) == tracks


def test_playing_row_uses_visible_sorted_order(qapp) -> None:
    playback = PlaybackStub()
    vm = PlaylistViewModel(playback)
    vm.set_playlist(UserPlaylist("Мой", _tracks()))
    vm.set_sort_order("title_asc")

    asyncio.run(vm.play_at(0))

    assert playback.played[0].track_id == "2"
    assert [
        t.track_id for t in playback.playlist_manager.current_playlist.tracks.values
    ] == ["2", "3", "1"]


def test_shuffle_reorders_rows_and_playback(qapp, monkeypatch) -> None:
    playback = PlaybackStub()
    vm = PlaylistViewModel(playback)
    vm.set_playlist(UserPlaylist("Мой", _tracks()))
    monkeypatch.setattr(
        "quantis.ui.viewmodels.playlist_vm.random.shuffle", list.reverse
    )

    asyncio.run(vm.play_shuffled())

    assert [t.track_id for t in vm.model.all_tracks()] == ["3", "2", "1"]
    assert playback.played[0].track_id == "3"
    assert [
        t.track_id for t in playback.playlist_manager.current_playlist.tracks.values
    ] == ["3", "2", "1"]


def test_removing_sorted_row_deletes_corresponding_source_track(
    qapp, monkeypatch
) -> None:
    playback = PlaybackStub()
    playlist = UserPlaylist("Мой", _tracks())
    vm = PlaylistViewModel(playback)
    vm.set_playlist(playlist)
    vm.set_sort_order("title_asc")

    async def remove_track(self, name, track):
        assert name == "Мой"
        assert track.track_id == "2"

    monkeypatch.setattr(
        "quantis.services.user_playlists.UserPlaylistsService.remove_track",
        remove_track,
    )
    assert asyncio.run(vm.remove_track_at(0)) is True
    assert [t.track_id for t in playlist.tracks.values] == ["1", "3"]
    assert [t.track_id for t in vm.model.all_tracks()] == ["3", "1"]


def test_sort_menu_changes_playlist_order(qapp) -> None:
    vm = PlaylistViewModel(PlaybackStub())
    page = PlaylistPage(vm)
    vm.set_playlist(UserPlaylist("Мой", _tracks()))

    sort_button = page.findChild(QPushButton, "playlistSort")
    assert sort_button is not None
    duration_action = next(
        action
        for action in sort_button.menu().actions()
        if action.text() == "Длительность: длинные сначала"
    )
    duration_action.trigger()

    assert [t.track_id for t in vm.model.all_tracks()] == ["2", "1", "3"]
    assert "Длительность" in sort_button.text()


def test_reload_same_playlist_keeps_selected_sort(qapp) -> None:
    vm = PlaylistViewModel(PlaybackStub())
    vm.set_playlist(UserPlaylist("Мой", _tracks()))
    vm.set_sort_order("title_asc")

    refreshed = _tracks() + [YandexTrack("4", "Бета", "Другой")]
    vm.set_playlist(UserPlaylist("Мой", refreshed))

    assert vm.sort_order == "title_asc"
    assert [t.track_id for t in vm.model.all_tracks()] == ["2", "4", "3", "1"]


def test_home_accepts_growth_of_active_sorted_recommendations(qapp) -> None:
    playback = PlaybackStub()
    home = HomeViewModel(history=object(), playback=playback, music=object())
    source = RecommendationPlaylist("Рекомендации", _tracks(), infinite=True)
    home._recommendation_playlist = source
    home._recommendation_model.set_tracks(list(source.tracks.values))
    working = RecommendationPlaylist(
        "Рекомендации", list(reversed(_tracks())), infinite=True
    )
    working.append_tracks([YandexTrack("4", "Новый", "Анна")])
    playback.playlist_manager.set_playlist(working)

    home.apply_queue_extended(working)

    assert [t.track_id for t in home._recommendation_model.all_tracks()] == [
        "1",
        "2",
        "3",
        "4",
    ]
