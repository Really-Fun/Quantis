"""Страница «Моя волна»: арт карточек, разделы, клики."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from quantis.models import YandexTrack
from quantis.models.playlist import WavePlaylist
from quantis.services.async_wave import (
    DEFAULT_WAVE_MOOD,
    WAVE_ACTIVITIES,
    WAVE_CHARACTER,
    WAVE_GENRES,
    WAVE_MOODS,
    WaveMood,
)
from quantis.ui import wave_art
from quantis.ui.viewmodels import home_vm
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.wave_page import WavePage, _CardFlow
from quantis.ui.wave_art import (
    WaveArtStore,
    mood_color,
    mood_kind,
    paint_wave_art,
    seed_asset_name,
    seed_asset_path,
)

_ARTIST = WaveMood(
    id="artist:643850",
    name="Lana Del Rey",
    seeds=("artist:643850",),
    cover_uri="avatars.yandex.net/get-music-content/1/a/%%",
)
_COMBO = WaveMood(
    id="mood:sad,activity:road-trip",
    name="Грущу в дороге",
    seeds=("mood:sad", "activity:road-trip"),
)
_GENRE = WaveMood(id="genre:tatar", name="Татарская музыка", seeds=("genre:tatar",))
_RESHUFFLE = WaveMood(
    id="diversity:reshuffle",
    name="Встряхнуть Мою волну",
    seeds=("diversity:reshuffle_1",),
    style="CONTROL_ACCENT",
)


def test_seed_asset_names() -> None:
    assert seed_asset_name("mood:calm") == "mood-calm"
    assert seed_asset_name("activity:road-trip") == "activity-road-trip"
    assert seed_asset_name("diversity:reshuffle_1791748022318") == "diversity-reshuffle"
    assert seed_asset_name("user:onyourwave") == "user-onyourwave"
    # родственные сиды берут картинку «родителя»
    assert seed_asset_name("genre:rusrock") == "genre-allrock"
    assert seed_asset_name("micro-genre:pop-rock") == "genre-pop"


def test_every_catalog_mood_and_control_has_its_own_art() -> None:
    catalog = (
        *WAVE_MOODS,
        *WAVE_ACTIVITIES,
        *WAVE_GENRES,
        *WAVE_CHARACTER,
        DEFAULT_WAVE_MOOD,
    )
    missing = [m.id for m in catalog if seed_asset_path(m.seeds[0]) is None]
    assert missing == []
    assert seed_asset_path("diversity:reshuffle_42") is not None
    assert seed_asset_path("genre:rusrock") is not None
    assert seed_asset_path("genre:tatar") is None


def test_mood_kinds() -> None:
    assert mood_kind(WAVE_MOODS[0]) == "mood"
    assert mood_kind(WAVE_ACTIVITIES[0]) == "activity"
    assert mood_kind(_COMBO) == "combo"
    assert mood_kind(_GENRE) == "genre"
    assert mood_kind(_ARTIST) == "artist"
    assert mood_kind(WAVE_CHARACTER[0]) == "character"
    assert mood_kind(DEFAULT_WAVE_MOOD) == "character"
    assert mood_kind(_RESHUFFLE) == "control"


def test_mood_color_falls_back_to_stable_vivid_hue() -> None:
    dark = WaveMood(id="artist:1", name="A", seeds=("artist:1",), color="#1a1a1a")
    first, second = mood_color(dark), mood_color(dark)
    assert first == second
    assert first.hsvSaturation() > 60
    assert mood_color(WAVE_MOODS[0]) == QColor("#2EC4B6")


def _render(mood: WaveMood, store: WaveArtStore) -> QImage:
    image = QImage(120, 160, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    painter = QPainter(image)
    paint_wave_art(painter, QRectF(0, 0, 120, 160), mood, store)
    painter.end()
    return image


def test_paint_uses_split_for_combo_and_generative_without_art(qapp) -> None:
    store = WaveArtStore()
    assert len(store.seed_images(_COMBO)) == 2
    combo = _render(_COMBO, store)
    # левый верх — грусть (синяя), правый низ — дорога: картинки разные
    assert combo.pixelColor(10, 10) != combo.pixelColor(110, 150)

    genre = _render(_GENRE, store)
    assert genre.pixelColor(60, 80).alpha() == 255  # процедурный фон без дыр
    assert _render(_GENRE, store).pixelColor(30, 40) == genre.pixelColor(30, 40)


def test_remote_cover_downloads_once_via_bridge(qapp, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(wave_art, "cache_dir", lambda: tmp_path)
    bridge = MagicMock()
    store = WaveArtStore()
    store.set_bridge(bridge)

    assert store.remote_image(_ARTIST) is None
    assert store.remote_image(_ARTIST) is None
    assert bridge.schedule.call_count == 1
    bridge.schedule.call_args.args[0].close()

    image = QImage(8, 8, QImage.Format.Format_RGB32)
    image.fill(QColor("red"))
    url = _ARTIST.cover_url("400x400")
    path = WaveArtStore._cache_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path), "PNG")
    assert WaveArtStore().remote_image(_ARTIST) is not None


def test_card_flow_stretches_cards_to_row(qapp) -> None:
    flow = _CardFlow()
    cols, card_w, card_h = flow.card_size(1200)
    assert cols == 6
    assert flow.MIN_W <= card_w <= flow.MAX_W
    assert 5 * flow.GAP + 6 * card_w <= 1200
    assert card_h > card_w
    assert flow.card_size(100)[0] == 1


def _vm(monkeypatch) -> tuple[HomeViewModel, MagicMock, MagicMock]:
    monkeypatch.setattr(home_vm, "yandex_token", lambda: "token")
    music = MagicMock()
    music.wave.fetch_wheel = AsyncMock(return_value=[_ARTIST, _RESHUFFLE, _GENRE])
    playback = MagicMock()
    playback.play_track = AsyncMock()
    playback.playlist_manager.current_playlist = None
    vm = HomeViewModel(MagicMock(), playback, music=music)
    return vm, music, playback


@pytest.mark.asyncio
async def test_page_builds_sections_and_hero(qapp, monkeypatch) -> None:
    vm, _music, _playback = _vm(monkeypatch)
    page = WavePage(vm, bridge=None)
    await vm.refresh_wave_moods()

    picks = [card.mood for card in page._picks.cards()]
    assert picks == [_ARTIST, _GENRE]  # «Встряхнуть» — кнопка шапки, не карточка
    assert [c.mood for c in page._moods.cards()] == list(WAVE_MOODS)
    assert [c.mood for c in page._activities.cards()] == list(WAVE_ACTIVITIES)
    assert [c.mood for c in page._genres.cards()] == list(WAVE_GENRES)
    assert page._hero._mood == DEFAULT_WAVE_MOOD
    assert not page._hero._reset.isVisibleTo(page)


@pytest.mark.asyncio
async def test_active_wave_is_marked_and_click_toggles_pause(qapp, monkeypatch) -> None:
    vm, _music, playback = _vm(monkeypatch)
    calm = WAVE_MOODS[0]
    wave = WavePlaylist(
        name=calm.name,
        tracks=[YandexTrack(track_id="1", title="t", author="a")],
        seeds=calm.seeds,
    )
    vm._wave_playlist = wave
    playback.playlist_manager.current_playlist = wave
    bridge = MagicMock()
    page = WavePage(vm, bridge=bridge)
    page.set_playing(True)

    active = [c.mood for c in page._moods.cards() if c._active]
    assert active == [calm]
    assert page._hero._mood == calm
    assert page._hero._reset.isVisibleTo(page)
    assert page._hero._play.text().endswith("Пауза")

    toggles: list[bool] = []
    page.toggle_pause_requested.connect(lambda: toggles.append(True))
    page._on_mood(calm)
    assert toggles == [True]
    bridge.schedule.assert_not_called()

    page._on_mood(WAVE_MOODS[1])
    bridge.schedule.assert_called_once()
    bridge.schedule.call_args.args[0].close()
