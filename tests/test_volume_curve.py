"""Логарифмическая шкала ползунка громкости."""

from __future__ import annotations

from quantis.player.volume import (
    output_gain,
    output_percent,
    ui_volume_to_linear_gain,
)


def test_slider_zero_is_silence() -> None:
    assert ui_volume_to_linear_gain(0) == 0.0
    assert output_percent(0) == 0


def test_slider_full_is_unity() -> None:
    assert abs(ui_volume_to_linear_gain(100) - 1.0) < 1e-9
    assert output_percent(100) == 100


def test_mid_slider_is_much_quieter_than_linear() -> None:
    mid = ui_volume_to_linear_gain(50)
    default = ui_volume_to_linear_gain(80)
    assert 0.05 < mid < 0.07
    assert 0.30 < default < 0.33
    assert default < 0.80


def test_duck_scales_linear_output() -> None:
    assert abs(output_gain(100, 0.5) - 0.5) < 1e-9
    assert output_percent(100, 0.25) == 25
    assert output_percent(80, 0.5) == round(ui_volume_to_linear_gain(80) * 50)
