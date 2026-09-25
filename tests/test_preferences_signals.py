"""Каждая настройка шлёт свой сигнал; громкость не «применяет тему»."""

from __future__ import annotations

from collections import Counter

import pytest
from PySide6.QtCore import QByteArray, QSettings

from quantis.models.repeat_mode import RepeatMode
from quantis.ui.preferences import UiPreferences

_SIGNALS = (
    "changed",
    "theme_changed",
    "wallpaper_changed",
    "layout_changed",
    "eco_changed",
    "volume_changed",
)


@pytest.fixture
def prefs(qapp):
    QSettings("ReallyFun", "Quantis").clear()
    UiPreferences._instance = None
    yield UiPreferences()
    UiPreferences._instance = None
    QSettings("ReallyFun", "Quantis").clear()


@pytest.fixture
def emitted(prefs: UiPreferences) -> Counter[str]:
    counter: Counter[str] = Counter()
    for name in _SIGNALS:
        getattr(prefs, name).connect(lambda *_, n=name: counter.update([n]))
    return counter


def test_volume_emits_only_volume_changed(
    prefs: UiPreferences, emitted: Counter[str]
) -> None:
    for value in range(30, 60):
        prefs.set_volume(value)
    assert emitted == Counter(volume_changed=30)


def test_silent_settings(prefs: UiPreferences, emitted: Counter[str]) -> None:
    prefs.set_repeat_mode(RepeatMode.TRACK)
    prefs.set_window_geometry(QByteArray(b"geometry"))
    prefs.set_update_check_on_startup(False)
    prefs.set_update_last_check_at(1.0)
    prefs.set_update_last_tag("v9")
    prefs.set_update_last_html_url("https://example.com")
    prefs.set_update_dismissed_tag("v9")
    assert emitted == Counter()


@pytest.mark.parametrize(
    ("apply", "signal"),
    [
        (lambda p: p.set_ui_theme("light"), "theme_changed"),
        (lambda p: p.set_wallpaper_enabled(True), "wallpaper_changed"),
        (lambda p: p.set_wallpaper_path("/tmp/wall.png"), "wallpaper_changed"),
        (lambda p: p.set_dynamic_wallpaper_enabled(True), "wallpaper_changed"),
        (lambda p: p.set_dynamic_wallpaper_fps(15), "wallpaper_changed"),
        (lambda p: p.set_backdrop_dim(0.6), "wallpaper_changed"),
        (lambda p: p.set_backdrop_blur(0.4), "wallpaper_changed"),
        (lambda p: p.set_backdrop_mode("video"), "wallpaper_changed"),
        (lambda p: p.set_backdrop_mode("cover"), "wallpaper_changed"),
        (lambda p: p.set_backdrop_motion(False), "wallpaper_changed"),
        (lambda p: p.set_show_now_playing_panel(False), "layout_changed"),
        (lambda p: p.set_show_home_featured_panel(False), "layout_changed"),
        (lambda p: p.set_background_eco_enabled(False), "eco_changed"),
    ],
)
def test_setting_emits_its_signal_and_changed(
    prefs: UiPreferences, emitted: Counter[str], apply, signal: str
) -> None:
    apply(prefs)
    # changed остаётся для плагинов.
    assert emitted == Counter({signal: 1, "changed": 1})


def test_same_value_is_silent(prefs: UiPreferences, emitted: Counter[str]) -> None:
    prefs.set_ui_theme(prefs.ui_theme)
    prefs.set_volume(prefs.volume)
    assert emitted == Counter()


def test_app_does_not_subscribe_to_changed() -> None:
    """Внутри приложения слушаем только конкретные сигналы."""
    from pathlib import Path

    import quantis

    root = Path(quantis.__file__).parent
    offenders = [
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if ".changed.connect(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
