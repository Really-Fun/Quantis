from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, QSettings, QSize
from PySide6.QtGui import QColor, QImage

from quantis.ui.preferences import UiPreferences
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor
from quantis.ui.views.widgets.backdrop_panel import (
    BackdropPanel,
    BackdropTiles,
    apply_backdrop_file,
    backdrop_kind,
)
from quantis.ui.views.widgets.wallpaper_backdrop import WallpaperBackdrop


@pytest.fixture
def prefs(qapp):
    QSettings("ReallyFun", "Quantis").clear()
    UiPreferences._instance = None
    yield UiPreferences()
    UiPreferences._instance = None
    QSettings("ReallyFun", "Quantis").clear()


def _image(tmp_path: Path) -> str:
    img = QImage(40, 30, QImage.Format.Format_RGB32)
    img.fill(QColor("#3366cc"))
    path = tmp_path / "wall.png"
    img.save(str(path))
    return str(path)


def test_file_kinds() -> None:
    assert backdrop_kind("/a/b.JPG") == "image"
    assert backdrop_kind("clip.mkv") == "video"
    assert backdrop_kind("notes.txt") is None


def test_dropped_image_and_video_become_backdrop(prefs, tmp_path) -> None:
    path = _image(tmp_path)
    assert apply_backdrop_file(prefs, path)
    assert prefs.backdrop_mode == "image" and prefs.wallpaper_path == path
    # раздел «Обои» в настройках видит то же состояние
    assert prefs.wallpaper_enabled

    assert apply_backdrop_file(prefs, "/videos/loop.mp4")
    assert prefs.backdrop_mode == "video" and prefs.backdrop_video_is_file
    assert not prefs.dynamic_wallpaper_enabled  # клипы треков выключены
    assert not apply_backdrop_file(prefs, "/tmp/readme.txt")

    # «Клип» из панели — снова клипы треков с YouTube
    prefs.set_backdrop_mode("video")
    assert prefs.dynamic_wallpaper_enabled and not prefs.backdrop_video_is_file


def test_tiles_pick_modes(prefs, qapp) -> None:
    comp = BackdropCompositor()
    panel = BackdropPanel(comp, prefs)
    tiles = panel.findChild(BackdropTiles)
    assert tiles is not None
    picked: list[str] = []
    tiles.picked.connect(picked.append)
    tw, th, gap, lh = tiles.TW, tiles.TH, tiles.GAP, tiles.LH
    assert tiles.mode_at(QPointF(10, 10)) == "palette"
    assert tiles.mode_at(QPointF(tw + gap + 10, 10)) == "cover"
    assert tiles.mode_at(QPointF(10, th + lh + gap + 10)) == "image"
    assert tiles.mode_at(QPointF(tw + gap + 10, th + lh + gap + 10)) == "video"

    panel.on_pick("cover")
    assert prefs.backdrop_mode == "cover"
    panel.on_pick("video")
    assert prefs.backdrop_mode == "video" and prefs.dynamic_wallpaper_enabled
    comp.set_wallpaper(QImage(QSize(8, 8), QImage.Format.Format_RGB32))
    panel.on_pick("image")  # картинка уже есть — просто включаем
    assert prefs.backdrop_mode == "image"


def test_sliders_and_motion_follow_preferences(prefs, qapp) -> None:
    panel = BackdropPanel(BackdropCompositor(), prefs)
    prefs.set_backdrop_mode("cover")
    prefs.set_backdrop_dim(0.7)
    assert panel._dim.value() == 70
    panel._blur.setValue(40)
    assert prefs.backdrop_blur == pytest.approx(0.4)
    assert not panel._motion_row.isHidden()
    panel._motion.click()
    assert prefs.backdrop_motion is False
    prefs.set_backdrop_mode("palette")
    assert panel._motion_row.isHidden()  # «Движение» — только у обложки


def test_own_video_survives_dynamic_toggle(qapp) -> None:
    backdrop = WallpaperBackdrop()
    backdrop.play_file_loop("/videos/loop.mp4")
    assert backdrop._video_active
    # контроллер клипов треков выключает видео-обои — свой клип не трогаем
    backdrop.set_dynamic_wallpaper_enabled(False)
    assert backdrop._video_active
    backdrop.stop_file_loop()
    assert not backdrop._video_active
