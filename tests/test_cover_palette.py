from __future__ import annotations

import time

from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QWidget

from quantis.ui.cover_accent import (
    CoverPalette,
    _hue_gap,
    palette_from_accent,
    palette_from_cover_path,
    palette_from_image,
)
from quantis.ui.live_palette import TRANSITION_MS, LivePalette


def _two_tone(left: str, right: str) -> QImage:
    img = QImage(60, 60, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.fillRect(0, 0, 40, 60, QColor(left))
    p.fillRect(40, 0, 20, 60, QColor(right))
    p.end()
    return img


def test_palette_needs_an_image(qapp, tmp_path) -> None:
    assert palette_from_image(None) is None
    assert palette_from_image(QImage()) is None
    assert palette_from_cover_path(tmp_path / "missing.jpg") is None


def test_palette_takes_two_distinct_hues(qapp) -> None:
    palette = palette_from_image(_two_tone("#e0206a", "#20c0e0"))
    assert palette is not None
    assert abs(palette.accent.hsvHueF() - QColor("#e0206a").hsvHueF()) < 0.03
    assert _hue_gap(palette.accent.hsvHueF(), palette.accent2.hsvHueF()) > 0.07
    # глубокий тон — того же оттенка, но тёмный: под фон
    assert palette.deep.valueF() < 0.5


def test_grey_cover_gives_neutral_palette(qapp) -> None:
    palette = palette_from_image(_two_tone("#808080", "#303030"))
    assert palette is not None
    assert palette.accent.hsvSaturationF() < 0.25


def test_palette_from_accent_keeps_accent(qapp) -> None:
    color = QColor("#6C5CE7")
    palette = palette_from_accent(color)
    assert palette.accent == color
    assert palette.accent2 != color


def test_live_palette_jump_and_transition(qapp) -> None:
    live = LivePalette()
    frames: list[CoverPalette] = []
    live.palette_changed.connect(frames.append)
    a = palette_from_accent(QColor("#ff0000"))
    b = palette_from_accent(QColor("#0000ff"))

    live.set_target(a, animate=False)
    assert frames == [a] and live.current == a and not live.is_animating()

    frames.clear()
    live.set_target(b)
    deadline = time.monotonic() + TRANSITION_MS / 1000 + 1.0
    while live.is_animating() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert not live.is_animating()
    assert frames[-1] == b and live.current == b
    assert len(frames) > 3  # были промежуточные кадры
    assert a not in frames
    assert len(set(frames)) == len(frames)  # одинаковые кадры не рассылаются


def test_transition_frames_do_not_restyle(qapp, monkeypatch) -> None:
    """Кадры перехода не должны вызывать setStyleSheet (уроки производительности)."""
    from quantis.ui.views.widgets.background_frame import BackgroundFrame

    calls = {"n": 0}
    original = QWidget.setStyleSheet

    def counted(self, sheet):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        original(self, sheet)

    frame = BackgroundFrame()
    live = LivePalette()
    live.palette_changed.connect(frame.set_palette)
    monkeypatch.setattr(QWidget, "setStyleSheet", counted)
    live.set_target(palette_from_accent(QColor("#00ff88")))
    deadline = time.monotonic() + TRANSITION_MS / 1000 + 1.0
    while live.is_animating() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    assert calls["n"] == 0
