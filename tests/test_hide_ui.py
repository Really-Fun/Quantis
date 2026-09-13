from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QWidget

from quantis.ui.main_window import is_typing_target
from quantis.ui.views.widgets.wallpaper_backdrop import BodyWithWallpaper


def test_is_typing_target_detects_inputs(qapp) -> None:
    line = QLineEdit()
    combo = QComboBox()
    label = QLabel("ok")
    assert is_typing_target(line) is True
    assert is_typing_target(combo) is True
    assert is_typing_target(label) is False
    assert is_typing_target(None) is False


def test_is_typing_target_walks_parents(qapp) -> None:
    parent = QLineEdit()
    child = QWidget(parent)
    assert is_typing_target(child) is True


def test_theater_mode_hides_foreground(qapp) -> None:
    body = BodyWithWallpaper()
    assert not body._foreground.isHidden()
    body.set_theater_mode(True)
    assert body._foreground.isHidden()
    assert body._layer_host.isHidden()
    assert body._backdrop._video_surface._cinematic is True
    assert body._backdrop._video_surface._opacity == 1.0
    body.set_theater_mode(False)
    assert not body._foreground.isHidden()
    assert not body._layer_host.isHidden()
    assert body._backdrop._video_surface._cinematic is False
    assert body._backdrop._video_surface._opacity == 0.28
