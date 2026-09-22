"""Unit-тесты модели Track."""

from __future__ import annotations

from quantis.models import SoundCloudTrack, YandexTrack, YoutubeTrack


def test_track_equality_includes_source() -> None:
    yandex = YandexTrack(track_id="123", title="T", author="A")
    youtube = YoutubeTrack(track_id="123", title="T", author="A")

    assert yandex != youtube
    assert hash(yandex) != hash(youtube)


def test_same_source_tracks_equal() -> None:
    first = YandexTrack(track_id="1", title="A", author="B")
    second = YandexTrack(track_id="1", title="X", author="Y")

    assert first == second


def test_soundcloud_not_equal_to_yandex() -> None:
    yandex = YandexTrack(track_id="123", title="T", author="A")
    soundcloud = SoundCloudTrack(track_id="123", title="T", author="A")

    assert yandex != soundcloud
    assert soundcloud.source == "soundcloud"
