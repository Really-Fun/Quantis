"""Главная: «Моя волна» рядом со сценой, пока очередь пуста."""

from __future__ import annotations

from unittest.mock import MagicMock

from quantis.models import Track
from quantis.services.async_wave import WaveMood
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.home_page import HomePage
from quantis.ui.views.widgets.now_playing_stage import UpNextItem
from quantis.ui.views.widgets.wave_card import WaveCard

_CALM = WaveMood(id="mood:calm", name="Спокойно", seeds=("mood:calm",))


def test_wave_card_states_and_actions(qapp) -> None:
    card = WaveCard()
    card.set_state(track_count=0, loading=True)
    assert card.status_text == "Загружаем…"
    assert not card.play_button.isEnabled()
    card.set_state(track_count=5)
    assert card.status_text == "5 в потоке"
    assert card.play_button.isEnabled()
    card.set_state(track_count=0, error="Не удалось загрузить волну")
    assert card.status_text == "Не удалось загрузить волну"
    assert card.play_button.isEnabled()  # можно попробовать ещё раз

    played, opened, moods = [], [], []
    card.play_requested.connect(lambda: played.append(True))
    card.open_requested.connect(lambda: opened.append(True))
    card.mood_activated.connect(moods.append)
    card.play_button.click()
    card.open_button.click()
    card.set_moods([_CALM])
    card.moods.chips()[0].click()
    assert played == [True] and opened == [True] and moods == [_CALM]


def test_wave_card_stacks_buttons_when_narrow(qapp) -> None:
    from PySide6.QtWidgets import QBoxLayout

    card = WaveCard()
    card.setFixedSize(360, 316)  # главная задаёт карточке размер явно
    card.show()
    qapp.processEvents()
    assert card.actions_direction == QBoxLayout.Direction.LeftToRight
    card.setFixedSize(200, 316)
    qapp.processEvents()
    assert card.actions_direction == QBoxLayout.Direction.TopToBottom


def test_wave_card_hides_moods_row_without_moods(qapp) -> None:
    card = WaveCard()
    card.set_moods([])
    assert card.moods.isHidden()
    card.set_moods([_CALM])
    assert not card.moods.isHidden()


def _home(qapp) -> HomePage:
    vm = HomeViewModel(MagicMock(), MagicMock(), music=MagicMock())
    page = HomePage(vm)
    page.resize(1300, 900)
    page.show()
    qapp.processEvents()
    return page


def test_home_shows_wave_card_until_queue_has_tracks(qapp) -> None:
    page = _home(qapp)
    assert not page.wave_card.isHidden()
    assert page.up_next.isHidden()
    track = Track(track_id=1, title="T", author="A", source="yandex")
    page.set_up_next([UpNextItem(track=track, index=1)])
    qapp.processEvents()
    assert page.wave_card.isHidden()
    assert not page.up_next.isHidden()
    page.set_up_next([])
    qapp.processEvents()
    assert not page.wave_card.isHidden()


def test_home_has_no_separate_moods_section(qapp) -> None:
    page = _home(qapp)
    assert not hasattr(page, "_wave_moods_section")


def test_recent_and_recommendations_side_by_side_when_wide(qapp) -> None:
    page = _home(qapp)
    grid = page._lists_grid
    assert grid.getItemPosition(grid.indexOf(page._recommend_section))[:2] == (0, 1)
    page.resize(800, 900)
    qapp.processEvents()
    assert grid.getItemPosition(grid.indexOf(page._recommend_section))[:2] == (1, 0)


def test_playlist_shelf_is_one_ribbon_until_expanded(qapp) -> None:
    from quantis.models import UserPlaylist
    from quantis.ui.views.widgets.playlist_card import PlaylistShelf

    shelf = PlaylistShelf()
    shelf.resize(900, 300)
    shelf.show()
    shelf.set_playlists([UserPlaylist(f"П{i}", (), None) for i in range(18)])
    qapp.processEvents()
    assert not shelf.expanded
    assert not shelf.ribbon.isHidden() and shelf.grid.isHidden()
    assert len(shelf.ribbon_cards()) == 18
    assert shelf.ribbon.can_scroll_forward
    shelf.set_expanded(True)
    assert shelf.ribbon.isHidden() and not shelf.grid.isHidden()
    assert len(shelf.grid.items()) == 18
    shelf.set_expanded(False)
    assert not shelf.ribbon.isHidden()
