from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QListView,
    QPushButton,
    QWidget,
)

from quantis.ui.shortcuts import (
    ALT_PAGE_IDS,
    KEYBIND_HINTS,
    is_arrow_navigation_target,
    is_space_target,
    is_typing_target,
)
from quantis.ui.views.widgets.wallpaper_backdrop import BodyWithWallpaper


def test_is_typing_target_detects_inputs(qapp) -> None:
    line = QLineEdit()
    combo = QComboBox()
    label = QLabel("ok")
    assert is_typing_target(line) is True
    assert is_typing_target(combo) is True
    assert is_typing_target(label) is False
    assert is_typing_target(None) is False


def test_arrow_navigation_skips_lists(qapp) -> None:
    assert is_arrow_navigation_target(QListView()) is True
    assert is_arrow_navigation_target(QLabel("ok")) is False


def test_space_target_skips_buttons_and_lists(qapp) -> None:
    assert is_space_target(QPushButton("ok")) is True
    assert is_space_target(QListView()) is True
    assert is_space_target(QLabel("ok")) is False


def test_alt_pages_cover_nav_top() -> None:
    assert ALT_PAGE_IDS == (0, 1, 2, 3, 4)
    keys = {key for key, _ in KEYBIND_HINTS}
    assert {"S", "L", "R", "Пробел", "Alt+S", "Alt+M"} <= keys


def test_is_typing_target_walks_parents(qapp) -> None:
    parent = QLineEdit()
    child = QWidget(parent)
    assert is_typing_target(child) is True


def test_theater_mode_keeps_foreground(qapp) -> None:
    body = BodyWithWallpaper()
    assert not body._foreground.isHidden()
    body.set_theater_mode(True)
    assert not body._foreground.isHidden()
    assert not body._layer_host.isHidden()
    assert body._backdrop._video_surface._cinematic is True
    assert body._backdrop._video_surface._opacity == 1.0
    body.set_theater_mode(False)
    assert not body._foreground.isHidden()
    assert not body._layer_host.isHidden()
    assert body._backdrop._video_surface._cinematic is False
    assert body._backdrop._video_surface._opacity == 0.28
