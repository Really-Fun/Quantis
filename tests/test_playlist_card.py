from __future__ import annotations

from quantis.ui.views.widgets.playlist_card import (
    balanced_column_count,
    playlist_tracks_label,
    wrap_column_count,
)


def test_balanced_columns_avoid_a_lonely_last_tile() -> None:
    # 6 плиток, влезает 5: два ряда по 3, а не 5 + 1.
    assert balanced_column_count(1240, 200, 10, 6) == 3
    assert balanced_column_count(1240, 200, 10, 7) == 4  # 4 + 3
    assert balanced_column_count(1240, 200, 10, 5) == 5  # один ряд — как есть
    assert balanced_column_count(1240, 200, 10, 11) == 4  # 3 ряда: 4 + 4 + 3
    assert balanced_column_count(0, 200, 10, 4) == 1
    # Одна плитка — ширины одной колонки полного ряда, а не во всю ширину.
    assert balanced_column_count(1240, 200, 10, 1) == 5


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
