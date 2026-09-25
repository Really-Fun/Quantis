from __future__ import annotations

from PySide6.QtCore import QRect, QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QWidget

from quantis.ui.image_fx import blur_image, fill_crop, mean_luma
from quantis.ui.themes import registry
from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor
from quantis.ui.views.widgets.wallpaper_backdrop import BodyWithWallpaper


def _solid(color: str, w: int = 64, h: int = 40) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def _compositor() -> tuple[BackdropCompositor, list[int]]:
    comp = BackdropCompositor(registry.get("classic"))
    comp.set_size(QSize(200, 120))
    hits: list[int] = []
    comp.frame_changed.connect(lambda: hits.append(1))
    return comp, hits


def test_frame_is_cached_until_something_changes(qapp) -> None:
    comp, hits = _compositor()
    first = comp.frame()
    assert first.size() == QSize(200, 120)
    assert comp.frame().cacheKey() == first.cacheKey()
    assert hits == []
    comp.set_phase(1.0)
    assert hits == [1]
    assert comp.frame().cacheKey() != first.cacheKey()


def test_video_frame_shows_only_when_active(qapp) -> None:
    comp, hits = _compositor()
    base = comp.frame().pixelColor(100, 60)
    comp.set_video_frame(_solid("#ffffff"))
    assert hits == []  # видео не включено — фон не трогаем
    comp.set_video_active(True)
    lit = comp.frame().pixelColor(100, 60)
    assert lit.lightness() > base.lightness()
    comp.set_video_active(False)
    assert comp.frame().pixelColor(100, 60) == base


def test_cinematic_keeps_video_inside_content(qapp) -> None:
    comp, _ = _compositor()
    comp.set_video_frame(_solid("#ffffff"))
    comp.set_video_active(True)
    comp.set_content_rect(QRect(0, 20, 200, 80))
    comp.set_cinematic(True)
    frame = comp.frame()
    assert frame.pixelColor(100, 5) == QColor(0, 0, 0)  # шапка — чёрная
    assert frame.pixelColor(100, 50).lightness() > 150  # контент — видео
    assert comp.video_opacity == 1.0


def test_body_reports_content_rect_to_shared_compositor(qapp) -> None:
    comp = BackdropCompositor()
    body = BodyWithWallpaper(compositor=comp)
    assert body.backdrop.compositor is comp
    body.resize(300, 200)
    body.show()  # скрытому виджету resizeEvent не приходит
    qapp.processEvents()
    assert comp._content.size() == QSize(300, 200)


def test_image_helpers(qapp) -> None:
    img = _solid("#336699", 100, 50)
    assert fill_crop(img, QSize(30, 30)).size() == QSize(30, 30)
    assert fill_crop(QImage(), QSize(30, 30)).isNull()
    assert blur_image(img, 0.5).size() == img.size()
    assert blur_image(img, 0.0) is img
    assert 0.0 < mean_luma(img) < 1.0
    assert mean_luma(_solid("#ffffff")) > 0.99


def test_glass_theme_tokens_and_rules(qapp) -> None:
    from quantis.ui.themes import qss

    neon, editorial = registry.get("neon"), registry.get("editorial")
    assert neon.has_glass and not editorial.has_glass
    assert neon.tokens()["panel_bg"] == "transparent"
    assert editorial.tokens()["panel_bg"] == editorial.colors.surface
    # радиус стекла берётся из итогового QSS темы, с учётом extra_qss
    glass = registry.get("glass")
    assert qss.px(qss.rule(glass, "QFrame#nowPlayingPanel")["border-radius"]) == 20
    assert qss.px("none", 3.0) == 3.0 and qss.px("1px solid red") == 1.0


def test_glass_is_throttled_and_frozen_in_eco(qapp, monkeypatch) -> None:
    from quantis.ui.views.widgets import backdrop_compositor as bc

    comp, _ = _compositor()
    first = comp.glass()
    assert first.size() == QSize(100, 60)  # половинное разрешение
    now = [1000.0]
    monkeypatch.setattr(bc, "monotonic", lambda: now[0])
    comp._glass_at = now[0]
    comp.set_phase(2.0)
    assert comp.glass().cacheKey() == first.cacheKey()  # раньше интервала — старое
    now[0] += bc.GLASS_MIN_INTERVAL
    second = comp.glass()
    assert second.cacheKey() != first.cacheKey()
    comp.set_eco(True)
    now[0] += 10
    comp.set_phase(3.0)
    assert comp.glass().cacheKey() == second.cacheKey()  # эко: не пересчитываем


def test_glass_panel_paints_blurred_backdrop(qapp) -> None:
    from quantis.ui.views.widgets.background_frame import BackgroundFrame
    from quantis.ui.views.widgets.glass import install_glass

    for theme_id, expect in (("neon", True), ("editorial", False)):
        shell = BackgroundFrame(theme=registry.get(theme_id))
        shell.resize(300, 200)
        comp = shell.compositor
        comp.set_video_frame(_solid("#ff0000"))
        comp.set_video_active(True)
        panel = QWidget(shell.content_host())
        panel.setObjectName("glassPanel")
        panel.setGeometry(50, 50, 100, 80)
        install_glass(panel, "QFrame#glassPanel")
        shell.show()
        qapp.processEvents()
        red = shell.grab().toImage().pixelColor(100, 90).red()
        bg = comp.frame().pixelColor(100, 90).red()
        assert (red != bg) is expect  # стекло с тонировкой отличается от фона
