from __future__ import annotations

from PySide6.QtGui import QColor

from quantis.ui.cover_accent import palette_from_accent
from quantis.ui.live_palette import LivePalette
from quantis.ui.themes import registry
from quantis.ui.views.widgets.waveform_seek import WaveformSeekSlider


def test_capsule_radius_token() -> None:
    assert registry.get("neon").tokens()["radius_capsule"] == "26px"
    assert registry.get("editorial").tokens()["radius_capsule"] == "0px"


def test_waveform_played_part_uses_track_colors(qapp) -> None:
    LivePalette.instance().set_target(
        palette_from_accent(QColor("#ff0000")), animate=False
    )
    seek = WaveformSeekSlider()
    seek.resize(400, 30)
    seek.setRange(0, 100)
    seek.setValue(50)
    image = seek.grab().toImage()

    def most_saturated(x0: int, x1: int) -> QColor:
        pixels = [image.pixelColor(x, y) for x in range(x0, x1) for y in range(30)]
        return max(pixels, key=lambda c: c.hsvSaturation())

    played = most_saturated(170, 190)  # ближе к головке — цвет accent (красный)
    rest = most_saturated(300, 340)
    assert played.hsvSaturation() > 120 and played.red() > played.blue()
    assert rest.hsvSaturation() < 60  # несыгранное — приглушённые «чернила» темы


def test_waveform_shape_depends_on_track(qapp) -> None:
    a, b = WaveformSeekSlider(), WaveformSeekSlider()
    a.set_seed("yandex:1")
    b.set_seed("yandex:2")
    assert a._peaks != b._peaks
