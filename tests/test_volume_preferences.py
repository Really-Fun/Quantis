"""Unit-тесты сохранения громкости в UiPreferences."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QSettings

from quantis.ui.preferences import UiPreferences


@pytest.fixture(autouse=True)
def reset_preferences_singleton():
    settings = QSettings("ReallyFun", "Quantis")
    settings.remove("playback/volume")
    settings.remove("ui/dynamic_wallpaper_quality")
    settings.remove("ui/dynamic_wallpaper_fps")
    settings.remove("ui/dynamic_wallpaper_av_delay_ms")
    settings.sync()
    UiPreferences._instance = None
    yield
    UiPreferences._instance = None


def test_volume_defaults_to_80(qapp) -> None:
    prefs = UiPreferences()
    assert prefs.volume == 80


def test_volume_persists(qapp) -> None:
    prefs = UiPreferences()
    prefs.set_volume(42)
    assert prefs.volume == 42

    stored = QSettings("ReallyFun", "Quantis").value("playback/volume")
    assert int(stored) == 42


def test_volume_clamped(qapp) -> None:
    prefs = UiPreferences()
    prefs.set_volume(150)
    assert prefs.volume == 100
    prefs.set_volume(-10)
    assert prefs.volume == 0


def test_wallpaper_quality_and_fps_defaults(qapp) -> None:
    prefs = UiPreferences()
    assert prefs.dynamic_wallpaper_quality == 360
    assert prefs.dynamic_wallpaper_fps == 10


def test_wallpaper_quality_and_fps_persist(qapp) -> None:
    prefs = UiPreferences()
    prefs.set_dynamic_wallpaper_quality(1080)
    prefs.set_dynamic_wallpaper_fps(24)
    assert prefs.dynamic_wallpaper_quality == 1080
    assert prefs.dynamic_wallpaper_fps == 24

    stored = QSettings("ReallyFun", "Quantis")
    assert int(stored.value("ui/dynamic_wallpaper_quality")) == 1080
    assert int(stored.value("ui/dynamic_wallpaper_fps")) == 24


def test_wallpaper_av_delay_default_persist_and_clamp(qapp) -> None:
    prefs = UiPreferences()
    assert prefs.dynamic_wallpaper_av_delay_ms == 250
    prefs.set_dynamic_wallpaper_av_delay_ms(180)
    assert prefs.dynamic_wallpaper_av_delay_ms == 180
    prefs.set_dynamic_wallpaper_av_delay_ms(5000)
    assert prefs.dynamic_wallpaper_av_delay_ms == 1000
    prefs.set_dynamic_wallpaper_av_delay_ms(-5000)
    assert prefs.dynamic_wallpaper_av_delay_ms == -500


def test_tests_do_not_touch_real_settings(qapp) -> None:
    path = QSettings("ReallyFun", "Quantis").fileName()
    assert "quantis-test-settings-" in path


def test_wallpaper_quality_and_fps_clamped(qapp) -> None:
    prefs = UiPreferences()
    prefs.set_dynamic_wallpaper_quality(2160)
    prefs.set_dynamic_wallpaper_fps(120)
    assert prefs.dynamic_wallpaper_quality == 1080
    assert prefs.dynamic_wallpaper_fps == 60
