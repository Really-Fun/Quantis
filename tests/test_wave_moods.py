"""Лента настроений «Моей волны» на главной."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from quantis.models import YandexTrack
from quantis.models.playlist import WavePlaylist
from quantis.services.async_wave import WaveMood
from quantis.ui.viewmodels.home_vm import HomeViewModel
from quantis.ui.views.widgets.wave_moods import WaveMoodStrip

_RESHUFFLE = WaveMood(
    id="diversity:reshuffle",
    name="Встряхнуть Мою волну",
    seeds=("diversity:reshuffle_1",),
    style="CONTROL_ACCENT",
)
_CALM = WaveMood(
    id="mood:calm",
    name="Сохранять спокойствие",
    seeds=("mood:calm",),
    color="#E7338F",
)
_RUN = WaveMood(id="activity:run", name="Бежать", seeds=("activity:run",))


def test_strip_marks_active_wave_and_keeps_mark_on_click(qapp) -> None:
    strip = WaveMoodStrip()
    strip.set_moods([_RESHUFFLE, _CALM, _RUN], active_seeds=("mood:calm",))

    chips = strip.chips()
    assert [c.text() for c in chips] == [m.name for m in (_RESHUFFLE, _CALM, _RUN)]
    assert [c.isChecked() for c in chips] == [False, True, False]
    assert chips[0].property("control") is True

    emitted: list[WaveMood] = []
    strip.mood_activated.connect(emitted.append)
    chips[2].click()

    assert emitted == [_RUN]
    # отметка переедет, только когда волна реально переключится
    assert [c.isChecked() for c in chips] == [False, True, False]

    strip.set_moods([_RESHUFFLE, _CALM, _RUN], active_seeds=("activity:run",))
    assert strip.chips() == chips  # тот же список — чипы не пересоздаются
    assert [c.isChecked() for c in chips] == [False, False, True]


def test_strip_disables_chips_while_switching(qapp) -> None:
    strip = WaveMoodStrip()
    strip.set_moods([_CALM, _RUN], busy=True)
    assert not any(c.isEnabled() for c in strip.chips())
    strip.set_moods([_CALM, _RUN], busy=False)
    assert all(c.isEnabled() for c in strip.chips())


def test_control_chip_is_never_marked_active(qapp) -> None:
    strip = WaveMoodStrip()
    strip.set_moods([_RESHUFFLE], active_seeds=_RESHUFFLE.seeds)
    assert not strip.chips()[0].isChecked()


@pytest.mark.asyncio
async def test_play_wave_mood_starts_session_plays_and_refreshes_wheel(
    qapp, monkeypatch
) -> None:
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    wave = WavePlaylist(tracks=[track], seeds=("mood:calm",), session_id="S1")
    music = MagicMock()
    music.wave.start_wave = AsyncMock(return_value=wave)
    music.wave.fetch_wheel = AsyncMock(return_value=[_RUN, _CALM])
    playback = MagicMock()
    playback.play_track = AsyncMock()
    vm = HomeViewModel(MagicMock(), playback, music=music)
    changes: list[bool] = []
    vm.wave_moods_changed.connect(lambda: changes.append(vm.wave_mood_busy))

    await vm.play_wave_mood(_CALM)

    music.wave.start_wave.assert_awaited_once_with(("mood:calm",), taste=[])
    playback.play_track.assert_awaited_once_with(track)
    playing = playback.playlist_manager.set_playlist.call_args.args[0]
    assert isinstance(playing, WavePlaylist)
    assert playing.session_id == "S1"
    assert vm.active_wave_seeds == ("mood:calm",)
    music.wave.fetch_wheel.assert_awaited_once_with(("mood:calm",))
    assert vm.wave_moods == (_RUN, _CALM)
    assert changes == [True, False, False]


@pytest.mark.asyncio
async def test_play_wave_mood_failure_reports_error(qapp, monkeypatch) -> None:
    music = MagicMock()
    music.wave.start_wave = AsyncMock(return_value=None)
    music.wave.fetch_wheel = AsyncMock(return_value=[])
    playback = MagicMock()
    playback.play_track = AsyncMock()
    vm = HomeViewModel(MagicMock(), playback, music=music)
    errors: list[str] = []
    vm.error_occurred.connect(errors.append)

    await vm.play_wave_mood(_CALM)

    playback.play_track.assert_not_awaited()
    assert errors == ["Не удалось включить «Сохранять спокойствие»"]
    assert not vm.wave_mood_busy
