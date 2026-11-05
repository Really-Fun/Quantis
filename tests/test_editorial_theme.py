"""«Редакционная»: прямые углы везде, один красный акцент, обложки в строках."""

from __future__ import annotations

import re

from PySide6.QtCore import QModelIndex, QRect
from PySide6.QtGui import QImage, QPainter
from PySide6.QtWidgets import QStyleOptionViewItem

from quantis.models.track import YandexTrack
from quantis.ui.themes import qss, registry


def test_square_corners_only_in_theme_without_radius() -> None:
    editorial = registry.get("editorial")
    assert editorial.corner(22) == 0 and editorial.tokens()["r12"] == "0px"
    for theme in registry.all():
        if theme.id != "editorial":
            assert theme.corner(22) == 22 and theme.tokens()["r12"] == "12px"


def test_editorial_qss_has_no_rounded_corners() -> None:
    sheet = qss.render(registry.get("editorial"))
    radii = re.findall(r"radius\s*:\s*([^;]+);", sheet)
    assert radii and all(v.strip() in ("0", "0px") for v in radii), set(radii)


def test_editorial_has_single_red_accent() -> None:
    theme = registry.get("editorial")
    assert theme.fixed_accent
    assert theme.colors.accent_fallback.upper() == "#E63B2E"
    sheet = qss.render(theme).lower()
    for cyan in ("#00e5ff", "0, 229, 255", "0, 220, 255", "46, 230, 255"):
        assert cyan not in sheet
    for purple in ("#6c5ce7", "108, 92, 231"):
        assert purple not in sheet


def test_editorial_row_shows_cover(qapp, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from quantis.ui.models import TrackListModel
    from quantis.ui.preferences import UiPreferences
    from quantis.ui.views.widgets import track_card

    asked: list[str] = []
    monkeypatch.setattr(
        track_card,
        "request_track_cover",
        lambda track, size: asked.append(track.track_id),
    )
    prefs = UiPreferences()
    old = prefs.ui_theme
    prefs.set_ui_theme("editorial")
    try:
        model = TrackListModel()
        model.set_tracks([YandexTrack(track_id="42", title="T", author="A")])
        delegate = track_card.TrackCardDelegate()
        assert delegate._editorial
        image = QImage(600, 60, QImage.Format.Format_ARGB32)
        painter = QPainter(image)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 600, 56)
        delegate.paint(painter, option, model.index(0, 0, QModelIndex()))
        painter.end()
    finally:
        prefs.set_ui_theme(old)
    assert asked == ["42"]


def test_fixed_accent_palette_has_no_second_hue() -> None:
    from quantis.ui.cover_accent import fallback_palette

    editorial = fallback_palette(registry.get("editorial"))
    assert editorial.accent2.rgb() == editorial.accent.rgb()
    classic = fallback_palette(registry.get("classic"))
    assert classic.accent2.rgb() != classic.accent.rgb()
