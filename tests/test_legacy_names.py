"""Unit-тесты разбора старых имён файлов `ID_Название_Исполнитель.ext`."""

from __future__ import annotations

import pytest

# quantis.models первым: иначе сохраняется циклический импорт providers <-> models.
import quantis.models  # noqa: F401
from quantis.providers.legacy_names import (
    LegacyName,
    parse_legacy_name,
    parse_legacy_names,
)


def test_youtube_id_with_underscore() -> None:
    assert parse_legacy_name("a_b-c_d_e_f_Song_Artist.m4a") == LegacyName(
        "youtube", "a_b-c_d_e_f", "Song", "Artist"
    )


def test_youtube_plain() -> None:
    assert parse_legacy_name("1cnR-iFl3D0_Real For Me_Nikkie.m4a") == LegacyName(
        "youtube", "1cnR-iFl3D0", "Real For Me", "Nikkie"
    )


def test_yandex() -> None:
    assert parse_legacy_name("42_Song_Artist.mp3") == LegacyName(
        "yandex", "42", "Song", "Artist"
    )


def test_long_numeric_is_yandex() -> None:
    assert parse_legacy_name("12345678901_Song_A.mp3") == LegacyName(
        "yandex", "12345678901", "Song", "A"
    )


def test_soundcloud() -> None:
    assert parse_legacy_name("sc987_Song_A.mp3") == LegacyName(
        "soundcloud", "987", "Song", "A"
    )


def test_author_keeps_underscores_and_missing_author_is_empty() -> None:
    assert parse_legacy_name("42_Song_Some_Artist.mp3") == LegacyName(
        "yandex", "42", "Song", "Some_Artist"
    )
    assert parse_legacy_name("42_Song.mp3") == LegacyName("yandex", "42", "Song", "")


@pytest.mark.parametrize(
    "name",
    ["Artist - Song.mp3", "42_Song_A.webm", "42.mp3", "_x_y.mp3", "notes.txt"],
)
def test_not_legacy(name: str) -> None:
    assert parse_legacy_name(name) is None


def test_ambiguous_name_has_yandex_and_youtube_readings() -> None:
    assert parse_legacy_names("12345678_Ab_Song.mp3") == [
        LegacyName("yandex", "12345678", "Ab", "Song"),
        LegacyName("youtube", "12345678_Ab", "Song", ""),
    ]


def test_ambiguous_name_is_none_in_parse_legacy_name() -> None:
    assert parse_legacy_name("12345678_Ab_Song.mp3") is None


def test_plain_yandex_has_single_reading() -> None:
    assert parse_legacy_names("42_Song_Artist.mp3") == [
        LegacyName("yandex", "42", "Song", "Artist")
    ]


def test_youtube_has_single_reading() -> None:
    assert parse_legacy_names("a_b-c_d_e_f_Song_Artist.m4a") == [
        LegacyName("youtube", "a_b-c_d_e_f", "Song", "Artist")
    ]


def test_no_readings_is_empty_list() -> None:
    assert parse_legacy_names("42.mp3") == []
