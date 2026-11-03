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
