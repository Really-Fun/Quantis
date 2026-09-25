from __future__ import annotations

from dataclasses import replace

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
    comp.set_mode("video")
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
        comp.set_mode("video")
        comp.set_video_frame(_solid("#ff0000"))
        comp.set_video_active(True)
        panel = QWidget(shell.content_host())
        panel.setObjectName("glassPanel")
        panel.setGeometry(50, 50, 100, 80)
        install_glass(panel, "QFrame#glassPanel")
        shell.show()
        qapp.processEvents()
        shot, frame = shell.grab().toImage(), comp.frame()
        differs = any(
            shot.pixelColor(x, 90) != frame.pixelColor(x, 90) for x in (60, 100, 140)
        )
        assert differs is expect  # стекло с тонировкой отличается от фона


def _video_luma(comp: BackdropCompositor, color: str) -> float:
    comp.set_video_frame(_solid(color))
    comp.set_video_active(True)
    return mean_luma(comp.frame())


def test_bright_clip_gets_extra_dim_and_dark_clip_stays_visible(qapp) -> None:
    comp, _ = _compositor()
    comp.set_look(dim=0.0, blur=0.0)
    white = _video_luma(comp, "#ffffff")
    comp.set_video_active(False)
    grey = _video_luma(comp, "#606060")
    # белый кадр затемнён до читаемого уровня, а не остался белым
    assert white < 0.45
    # тёмный кадр не «съеден» затемнением: разница с белым меньше исходной
    assert abs(white - grey) < 1 - mean_luma(_solid("#606060"))


def test_dim_slider_darkens(qapp) -> None:
    comp, _ = _compositor()
    comp.set_look(dim=0.0, blur=0.0)
    light = _video_luma(comp, "#3070a0")
    comp.set_look(dim=1.0, blur=0.0)
    assert mean_luma(comp.frame()) < light


def test_clip_luma_is_smoothed_between_frames(qapp) -> None:
    comp, _ = _compositor()
    comp.set_look(dim=0.0, blur=0.0)
    _video_luma(comp, "#101010")
    jump = _video_luma(comp, "#ffffff")  # один яркий кадр после тёмных
    comp.set_video_active(False)
    settled = _video_luma(comp, "#ffffff")  # клип сразу яркий
    assert jump > settled  # автозатемнение догоняет плавно, без мигания


def test_light_theme_lightens_instead_of_darkening(qapp) -> None:
    comp = BackdropCompositor(registry.get("light"))
    comp.set_size(QSize(200, 120))
    comp.set_mode("video")
    comp.set_look(dim=0.5, blur=0.0)
    assert _video_luma(comp, "#202020") > mean_luma(_solid("#202020"))


def test_no_glass_in_theater_mode(qapp) -> None:
    from PySide6.QtGui import QPainter, QPainterPath

    from quantis.ui.views.widgets.background_frame import BackgroundFrame
    from quantis.ui.views.widgets.glass import paint_glass

    shell = BackgroundFrame(theme=registry.get("neon"))
    shell.resize(300, 200)
    panel = QWidget(shell.content_host())
    panel.setGeometry(10, 10, 50, 50)
    path = QPainterPath()
    path.addRect(0, 0, 50, 50)
    target = QImage(50, 50, QImage.Format.Format_RGB32)
    painter = QPainter(target)
    assert paint_glass(panel, painter, path) is True
    shell.set_cinematic(True)
    assert paint_glass(panel, painter, path) is False
    painter.end()


def _cover() -> QImage:
    img = QImage(96, 96, QImage.Format.Format_RGB32)
    img.fill(QColor("#e02090"))
    return img


def test_cover_mode_and_clip_fallback_show_cover(qapp) -> None:
    comp, _ = _compositor()
    comp.set_mode("palette")
    soft = comp.frame().pixelColor(100, 60)
    comp.set_cover(_cover())
    assert comp.frame().pixelColor(100, 60) == soft  # цвета трека: обложку не видно
    comp.set_mode("cover")
    assert comp.frame().pixelColor(100, 60).red() > soft.red() + 20
    # клип ещё грузится — вместо него та же обложка
    comp.set_mode("video")
    assert comp.frame().pixelColor(100, 60).red() > soft.red() + 20
    comp.set_video_frame(_solid("#20e040"))
    comp.set_video_active(True)
    assert (
        comp.frame().pixelColor(100, 60).green()
        > comp.frame().pixelColor(100, 60).red()
    )


def test_drift_runs_only_when_cover_is_visible(qapp) -> None:
    comp, _ = _compositor()
    comp.set_mode("cover")
    assert not comp.needs_drift()  # нет обложки — нечему плыть
    comp.set_cover(_cover())
    assert comp.needs_drift()
    before = comp.frame().cacheKey()
    comp.advance_drift(1.0)
    assert comp.frame().cacheKey() != before
    comp.set_motion(False)
    assert not comp.needs_drift()
    comp.set_motion(True)
    comp.set_eco(True)
    assert not comp.needs_drift()
    comp.set_eco(False)
    comp.set_mode("image")
    assert not comp.needs_drift()


def test_backdrop_mode_maps_to_existing_wallpaper_settings(qapp) -> None:
    from PySide6.QtCore import QSettings

    from quantis.ui.preferences import UiPreferences

    QSettings("ReallyFun", "Quantis").clear()
    UiPreferences._instance = None
    prefs = UiPreferences()
    try:
        assert prefs.backdrop_mode == "palette"
        prefs.set_backdrop_mode("video")
        assert prefs.dynamic_wallpaper_enabled and not prefs.wallpaper_enabled
        prefs.set_backdrop_mode("image")
        assert prefs.wallpaper_enabled and not prefs.dynamic_wallpaper_enabled
        prefs.set_backdrop_mode("cover")
        assert prefs.backdrop_mode == "cover"
        assert not prefs.wallpaper_enabled and not prefs.dynamic_wallpaper_enabled
        # раздел «Обои» включил видео — панель «Фон» видит «Клип»
        prefs.set_dynamic_wallpaper_enabled(True)
        assert prefs.backdrop_mode == "video"
        prefs.set_dynamic_wallpaper_enabled(False)
        assert prefs.backdrop_mode == "cover"  # выбор «обложка» запомнился
    finally:
        UiPreferences._instance = None
        QSettings("ReallyFun", "Quantis").clear()


def test_glass_samples_backdrop_under_the_panel(qapp) -> None:
    """Стекло берёт из фона ровно то, что под панелью: без сдвига, масштаба и
    повторов текстуры (панель далеко от края, фон — горизонтальный градиент)."""
    from PySide6.QtGui import QLinearGradient, QPainter, QPainterPath

    from quantis.ui.views.widgets.background_frame import BackgroundFrame
    from quantis.ui.views.widgets.glass import paint_glass

    shell = BackgroundFrame(theme=registry.get("neon"))
    shell.resize(800, 200)
    shell.show()  # иначе resizeEvent не придёт и кадр будет 1×1
    qapp.processEvents()
    comp = shell.compositor
    comp.set_theme(replace(registry.get("neon"), glass_blur=0.011))  # почти без размытия
    comp.set_look(dim=0.0, blur=0.0)
    ramp = QImage(800, 200, QImage.Format.Format_RGB32)
    fill = QPainter(ramp)
    gradient = QLinearGradient(0, 0, 800, 0)
    gradient.setColorAt(0, QColor(0, 0, 0))
    gradient.setColorAt(1, QColor(255, 255, 255))
    fill.fillRect(ramp.rect(), gradient)
    fill.end()
    comp.set_mode("image")
    comp.set_wallpaper(ramp)
    panel = QWidget(shell.content_host())
    panel.setGeometry(300, 50, 400, 100)
    path = QPainterPath()
    path.addRect(0, 0, 400, 100)
    out = QImage(400, 100, QImage.Format.Format_RGB32)
    painter = QPainter(out)
    assert paint_glass(panel, painter, path, QColor(0, 0, 0, 0), sheen=False)
    painter.end()
    frame = comp.frame()
    for x in (10, 150, 300, 390):
        got, want = out.pixelColor(x, 50), frame.pixelColor(300 + x, 100)
        assert abs(got.lightness() - want.lightness()) < 12, (x, got, want)
