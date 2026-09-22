"""PlayerViewModel: таймер не должен тикать прошлый трек до старта нового."""

from __future__ import annotations

from unittest.mock import MagicMock

from quantis.models import YoutubeTrack
from quantis.plugins.event_bus import EventBus
from quantis.ui.viewmodels.player_vm import PlayerViewModel


def test_track_change_resets_slider_until_audio_live(qapp) -> None:
    player = MagicMock()
    player.current_source = "https://cdn.example/old.mp3"
    player.time = 95_000
    player.duration = 180_000
    player.on_pause = False

    playback = MagicMock()
    playback.audio_live = False
    playback.is_seeking = False

    event_bus = EventBus()
    vm = PlayerViewModel(playback, player, event_bus)
    positions: list[int] = []
    durations: list[int] = []
    vm.position_changed.connect(positions.append)
    vm.duration_changed.connect(durations.append)

    track = YoutubeTrack(
        track_id="dQw4w9WgXcQ",
        title="Song",
        author="Artist",
        duration_ms=201_000,
    )
    event_bus.track_changed.emit(track)
    vm._update_timeline()

    assert positions == [0]
    assert durations == [201_000]

    playback.audio_live = True
    player.time = 0
    player.duration = 201_000
    vm._update_timeline()
    assert positions[-1] == 0
