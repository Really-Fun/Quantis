from __future__ import annotations

from PySide6.QtCore import QPointF

from quantis.models.playlist import Playlist
from quantis.models.track import YandexTrack, YoutubeTrack
from quantis.ui.views.widgets.now_playing_stage import (
    NowPlayingStage,
    UpNextPanel,
    source_name,
    upcoming,
)
from quantis.ui.views.widgets.playlist_card import QuickPickShelf, WaveQuickTile


def _tracks(n: int) -> list[YandexTrack]:
    return [
        YandexTrack(track_id=f"t{i}", title=f"Трек {i}", author="A") for i in range(n)
    ]


def test_upcoming_follows_current_track_and_wraps() -> None:
    tracks = _tracks(6)
    items = upcoming(tracks, tracks[4], current_index=0)
    assert [i.index for i in items] == [5, 0, 1, 2]
    assert [i.track for i in items] == [tracks[5], tracks[0], tracks[1], tracks[2]]
    # трека нет в плейлисте — считаем от индекса плейлиста
    assert [i.index for i in upcoming(tracks, None, current_index=2)] == [3, 4, 5, 0]
    # короткая очередь: без повторов текущего
    assert [i.index for i in upcoming(tracks[:3], tracks[0], 0)] == [1, 2]
    assert upcoming(tracks[:1], tracks[0], 0) == []


def test_source_names() -> None:
    assert source_name("yandex") == "Яндекс"
    assert source_name("youtube") == "YouTube"
    assert source_name("") == "Файл"


def test_stage_modes_and_buttons(qapp) -> None:
    stage = NowPlayingStage()
    stage.show()
    assert stage.mode == "empty"
    assert stage._title.fullText() == "Выбери трек"
    assert not stage._wave_btn.isHidden() and not stage._search_btn.isHidden()
    assert stage._spectrum.isHidden()

    track = YoutubeTrack(track_id="x", title="Город не спит", author="Ретроград")
    stage.set_track(track, mode="resume")
    assert stage._kicker.text() == "Продолжить слушать"
    assert not stage._resume_btn.isHidden() and stage._wave_btn.isHidden()
    stage.set_track(track, mode="playing")
    assert stage._kicker.text() == "Сейчас играет"
    assert stage._resume_btn.isHidden() and not stage._spectrum.isHidden()


def test_stage_animates_only_while_playing_visible_and_not_eco(qapp) -> None:
    stage = NowPlayingStage()
    stage.set_track(_tracks(1)[0], mode="playing")
    stage.show()
    assert not stage.is_animating()  # пауза — пластинка и спектр стоят
    stage.set_playing(True)
    assert stage.is_animating()
    stage.set_eco(True)
    assert not stage.is_animating()
    stage.set_eco(False)
    assert stage.is_animating()
    stage.hide()
    assert not stage.is_animating()
    stage.show()
    stage.set_track(_tracks(1)[0], mode="resume")
    assert not stage.is_animating()


def test_up_next_click_plays_by_playlist_index(qapp) -> None:
    panel = UpNextPanel()
    tracks = _tracks(5)
    panel.set_items(upcoming(tracks, tracks[1], 0))
    hits: list[int] = []
    panel.track_activated.connect(hits.append)
    assert panel._row_at(QPointF(40, 62 + UpNextPanel.ROW * 1 + 10)) == 1
    panel.track_activated.emit(panel.items()[1].index)
    assert hits == [3]


class _Pl(Playlist):
    def __init__(self, name: str, kind: str | None = None) -> None:
        super().__init__(name, ())
        if kind:
            self.kind = kind  # type: ignore[attr-defined]

    def get_tracks(self):  # type: ignore[no-untyped-def]
        return ()


def test_wave_is_first_quick_tile_with_play_and_count(qapp) -> None:
    shelf = QuickPickShelf()
    shelf.set_wave_state(available=True, track_count=0, loading=True)
    shelf.set_playlists([_Pl("Любимые"), _Pl("Моя волна", "wave"), _Pl("Скачанные")])
    grid_items = shelf._grid._items
    assert isinstance(grid_items[0], WaveQuickTile)
    tile = shelf.wave_tile
    assert tile is not None and tile._subtitle.text() == "Загружаем…"
    assert not tile._play_btn.isEnabled()
    shelf.set_wave_state(available=True, track_count=5)
    assert tile._subtitle.text() == "5 в потоке" and tile._play_btn.isEnabled()
    played: list[bool] = []
    shelf.wave_play_requested.connect(lambda: played.append(True))
    tile._play_btn.click()
    assert played == [True]
