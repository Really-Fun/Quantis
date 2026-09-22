from __future__ import annotations

from quantis.ui.views.widgets.playlist_card import (
    playlist_tracks_label,
    wrap_column_count,
)


def test_playlist_tracks_label_plural() -> None:
    assert playlist_tracks_label(1) == "1 трек"
    assert playlist_tracks_label(2) == "2 трека"
    assert playlist_tracks_label(5) == "5 треков"
    assert playlist_tracks_label(21) == "21 трек"
    assert playlist_tracks_label(12) == "12 треков"


def test_wrap_column_count_fills_width() -> None:
    assert wrap_column_count(640, 200, 10, 6) == 3
    assert wrap_column_count(1260, 200, 10, 6) == 6
    assert wrap_column_count(400, 140, 16, 9) == 2
    assert wrap_column_count(0, 200, 10, 4) == 1
    assert wrap_column_count(900, 140, 16, 1) == 1
