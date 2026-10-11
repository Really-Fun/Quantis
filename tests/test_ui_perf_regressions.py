"""Регрессии плавности: лишние перерисовки окна и синхронные вызовы в UI."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from quantis.config import credentials
from quantis.models import YandexTrack
from quantis.models.playlist import RecentlyPlayedPlaylist
from quantis.ui.themes import registry
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor
from quantis.ui.views.widgets.playlist_card import QuickPickShelf


def _compositor(qapp) -> tuple[BackdropCompositor, list[int]]:
    comp = BackdropCompositor(registry.get("clear"))
    comp.set_size(QSize(200, 120), 1.0)
    emitted: list[int] = []
    comp.frame_changed.connect(lambda: emitted.append(1))
    return comp, emitted


def test_glow_pulse_does_not_repaint_window_under_wallpaper(qapp) -> None:
    comp, emitted = _compositor(qapp)
    image = QImage(64, 64, QImage.Format.Format_RGB32)
    image.fill(QColor("navy"))
    comp.set_wallpaper(image)
    comp.set_mode("image")
    emitted.clear()

    for step in range(1, 6):
        comp.set_phase(step * 0.012)

    # картинка закрывает слой темы — пульс не виден, окно не трогаем
    assert emitted == []


def test_glow_pulse_repaints_when_theme_layer_is_visible(qapp) -> None:
    comp, emitted = _compositor(qapp)
    comp.set_mode("palette")
    emitted.clear()
    comp.set_phase(0.5)
    assert emitted == [1]


def test_yandex_token_is_read_from_keyring_once(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get(service: str, user: str) -> str:
        calls.append(service)
        return "secret"

    monkeypatch.setattr(credentials, "get_password", fake_get)
    assert credentials.yandex_token() == "secret"
    assert credentials.yandex_token() == "secret"
    assert len(calls) == 1

    monkeypatch.setattr(credentials, "set_password", lambda *a: None)
    monkeypatch.setattr(credentials.Clients, "reload_yandex_client", lambda self: None)
    credentials.save_yandex_token(" new ")
    assert credentials.yandex_token() == "new"
    assert len(calls) == 1


def test_quick_shelf_keeps_tiles_when_only_tracks_change(qapp) -> None:
    shelf = QuickPickShelf()
    first = RecentlyPlayedPlaylist(
        tracks=[YandexTrack(track_id="1", title="a", author="x")]
    )
    shelf.set_playlists([first])
    tile = shelf._grid.items()[0]

    second = RecentlyPlayedPlaylist(
        tracks=[YandexTrack(track_id="2", title="b", author="y")]
    )
    shelf.set_playlists([second])

    assert shelf._grid.items()[0] is tile  # плитка та же, не пересоздана
    assert tile.playlist is second  # но клик откроет свежий плейлист
