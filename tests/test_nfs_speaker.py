"""Скрипт диктора, фильтр волны и отмена TTS при skip."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal

from quantis.models import YandexTrack
from quantis.models.playlist import (
    DownloadPlaylist,
    LikedPlaylist,
    RecommendationPlaylist,
    WavePlaylist,
)
from quantis.plugins.loader import PluginLoader, PluginMeta

_PLUGIN = Path(__file__).resolve().parents[1] / "plugins_dir" / "nfs_dictor"
# plugins_dir не в git: плагины живут у разработчика локально.
if not _PLUGIN.is_dir():
    pytest.skip("нет plugins_dir/nfs_dictor", allow_module_level=True)
if str(_PLUGIN) not in sys.path:
    sys.path.insert(0, str(_PLUGIN))

from announcer import Announcer  # noqa: E402
from config import SpeakerConfig  # noqa: E402
from script import (  # noqa: E402
    FALLBACK_FACTS,
    build_script,
    first_sentence,
    is_radio_playlist,
    now_playing_line,
)
from wikipedia import fact_from_payload  # noqa: E402


class _ImmediateBridge:
    async def call_main(self, callback):
        return callback()


class _FakeOverlay(QObject):
    started = Signal()
    ended = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.played: list[str] = []
        self.stop_count = 0

    def play(self, path) -> None:
        self.played.append(str(path))
        self.started.emit()

    def stop(self) -> None:
        self.stop_count += 1

    def pause(self) -> None:
        return None

    def resume(self) -> None:
        return None


class _DuckPlayer:
    def __init__(self) -> None:
        self._duck = 1.0
        self.gains: list[float] = []

    def duck_gain(self) -> float:
        return self._duck

    def set_duck_gain(self, gain: float) -> None:
        self._duck = float(gain)
        self.gains.append(self._duck)


class _SilentFacts:
    async def fact_for(self, author: str) -> str | None:
        return None


def test_now_playing_line() -> None:
    assert now_playing_line("Breathe", "The Prodigy") == (
        "А сейчас играет «Breathe» — The Prodigy."
    )


def test_build_script_with_fact() -> None:
    text = build_script(
        "Breathe",
        "The Prodigy",
        "The Prodigy записали The Fat of the Land в 1997 году.",
    )
    assert text.startswith("The Prodigy записали The Fat of the Land в 1997 году.")
    assert "А сейчас играет «Breathe» — The Prodigy." in text


def test_build_script_fallback() -> None:
    text = build_script("Song", "Artist", None)
    assert text.startswith(FALLBACK_FACTS[0])
    assert "«Song» — Artist." in text


def test_first_sentence_trims() -> None:
    extract = (
        "The Prodigy — британская электронная группа. Они выпустили много альбомов."
    )
    assert first_sentence(extract) == "The Prodigy — британская электронная группа."


def test_first_sentence_long_clip() -> None:
    blob = "слово " * 80
    clipped = first_sentence(blob, max_len=50)
    assert len(clipped) <= 51
    assert clipped.endswith("…")


def test_is_radio_playlist() -> None:
    track = YandexTrack(track_id="1", title="A", author="B")
    assert is_radio_playlist(WavePlaylist(tracks=[track]))
    assert is_radio_playlist(RecommendationPlaylist(tracks=[track]))
    assert not is_radio_playlist(DownloadPlaylist(tracks=[track]))
    assert not is_radio_playlist(LikedPlaylist(tracks=[track]))
    assert not is_radio_playlist(None)


def test_fact_from_payload_skips_disambiguation() -> None:
    assert fact_from_payload({"type": "disambiguation", "extract": "Foo. Bar."}) is None
    assert (
        fact_from_payload({"type": "standard", "extract": "Группа из Лондона. Ещё."})
        == "Группа из Лондона."
    )


def test_plugin_class_loads(qapp) -> None:
    meta = PluginMeta(
        plugin_id="nfs_speaker",
        name="Need For Speed Speaker",
        version="0.1.0",
        author="Really-Fun",
        description="",
        path=_PLUGIN,
        entry=_PLUGIN / "plugin.py",
    )
    cls = PluginLoader(_PLUGIN.parent).load_class(meta)
    assert cls.name == "Need For Speed Speaker"


@pytest.mark.asyncio
async def test_announcer_skips_regular_playlist(tmp_path: Path, qapp) -> None:
    overlay = _FakeOverlay()
    player = _DuckPlayer()
    track = YandexTrack(track_id="1", title="Song", author="Artist")
    played: list[str] = []

    async def synth(text, dest, *, voice, rate):
        played.append(text)
        return dest

    announcer = Announcer(
        player,  # type: ignore[arg-type]
        overlay,
        _ImmediateBridge(),  # type: ignore[arg-type]
        tmp_path,
        playlist_of=lambda: DownloadPlaylist(tracks=[track]),
        facts=_SilentFacts(),
        synth=synth,
    )

    await announcer.handle_track(track)
    assert played == []
    assert overlay.played == []
    assert player.gains == [1.0]


@pytest.mark.asyncio
async def test_announcer_plays_on_wave_and_ducks(tmp_path: Path, qapp) -> None:
    overlay = _FakeOverlay()
    player = _DuckPlayer()
    track = YandexTrack(track_id="1", title="Breathe", author="The Prodigy")
    playlist = WavePlaylist(tracks=[track])

    async def synth(text, dest, *, voice, rate):
        return dest

    announcer = Announcer(
        player,  # type: ignore[arg-type]
        overlay,
        _ImmediateBridge(),  # type: ignore[arg-type]
        tmp_path,
        playlist_of=lambda: playlist,
        facts=_SilentFacts(),
        synth=synth,
    )
    announcer.set_config(SpeakerConfig(duck_gain=0.3))

    await announcer.handle_track(track)
    assert len(overlay.played) == 1
    assert player.gains[-1] == 0.3


@pytest.mark.asyncio
async def test_second_track_cancels_first_tts(tmp_path: Path, qapp) -> None:
    overlay = _FakeOverlay()
    player = _DuckPlayer()
    first = YandexTrack(track_id="1", title="One", author="A")
    second = YandexTrack(track_id="2", title="Two", author="B")
    playlist = WavePlaylist(tracks=[first, second])
    started = asyncio.Event()
    release = asyncio.Event()
    synthesized: list[str] = []

    async def synth(text, dest, *, voice, rate):
        synthesized.append(text)
        if "One" in text:
            started.set()
            await release.wait()
            return dest
        return dest

    announcer = Announcer(
        player,  # type: ignore[arg-type]
        overlay,
        _ImmediateBridge(),  # type: ignore[arg-type]
        tmp_path,
        playlist_of=lambda: playlist,
        facts=_SilentFacts(),
        synth=synth,
    )

    task = asyncio.create_task(announcer.handle_track(first))
    await started.wait()
    await announcer.handle_track(second)
    release.set()
    await task

    assert len(overlay.played) == 1
    assert any("Two" in line for line in synthesized)
    assert overlay.played[-1].endswith(".mp3")
