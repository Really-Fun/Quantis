from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage

from quantis.models.playlist import RecommendationPlaylist, UserPlaylist
from quantis.models.track import Track
from quantis.ui.views.widgets import playlist_art
from quantis.ui.views.widgets.playlist_art import (
    PlaylistArtLayer,
    compose_art,
    pick_art_path,
    placeholder_art,
)


def _save(path, width: int, height: int) -> str:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("white"))
    assert image.save(str(path))
    return str(path)


def _luma(image: QImage, x: int, y: int) -> int:
    return image.pixelColor(x, y).lightness()


def test_compose_keeps_art_on_the_right_and_dims_the_left(qapp) -> None:
    art = QImage(400, 400, QImage.Format.Format_RGB32)
    art.fill(QColor("white"))
    frame = compose_art(art, QSize(1200, 600), QColor("#0A0C10"))
    assert frame.size() == QSize(1200, 600)
    # слева под списком темно, справа арт почти не тронут
    assert _luma(frame, 60, 300) < 60
    assert _luma(frame, 1150, 300) > 200


def test_compose_without_size_or_art(qapp) -> None:
    assert compose_art(QImage(), QSize(0, 0), QColor("black")).isNull()
    frame = compose_art(QImage(), QSize(320, 180), QColor("#0A0C10"))
    assert frame.pixelColor(10, 90) == QColor("#0A0C10")


def test_pick_prefers_own_cover_then_large_track_cover(
    qapp, tmp_path, monkeypatch
) -> None:
    small, large = Track(1, "a", "x"), Track(2, "b", "y")
    files = {
        1: _save(tmp_path / "small.png", 480, 270),
        2: _save(tmp_path / "large.png", 1280, 720),
    }
    monkeypatch.setattr(
        playlist_art, "track_cover_file", lambda t: tmp_path / files[t.track_id]
    )
    # у подборки своя «обложка» — svg-значок, это не арт
    mix = RecommendationPlaylist("Микс", [small, large])
    assert pick_art_path(mix) == files[2]
    assert pick_art_path(RecommendationPlaylist("Микс", [small])) == files[1]

    own = _save(tmp_path / "own.png", 300, 300)
    assert pick_art_path(UserPlaylist("Мой", [small, large], own)) == own
    assert pick_art_path(RecommendationPlaylist("Пусто", [])) is None


def test_layer_falls_back_to_gradient_and_fades_in(qapp, tmp_path) -> None:
    layer = PlaylistArtLayer()
    layer.resize(640, 360)
    layer.set_art(None, "Микс дня")
    assert not layer.isVisible()
    layer.set_shown(True)
    assert layer.isVisible()
    layer._fade.setCurrentTime(layer._fade.duration())
    assert layer._opacity == 1.0
    assert layer.grab().toImage().pixelColor(600, 180) != QColor("black")
    # верх растворяется в фоне окна, ниже арт непрозрачен
    assert layer._frame.pixelColor(600, 0).alpha() < 8
    assert layer._frame.pixelColor(600, 200).alpha() == 255
    assert not placeholder_art("Микс дня").isNull()

    layer.set_shown(False)
    layer._fade.setCurrentTime(layer._fade.duration())
    assert not layer.isVisible()


def test_side_bars_of_youtube_music_covers_are_cropped(qapp) -> None:
    from PySide6.QtGui import QPainter

    from quantis.ui.views.widgets.playlist_art import crop_side_bars

    boxed = QImage(1280, 720, QImage.Format.Format_RGB32)
    boxed.fill(QColor("#205060"))  # поля
    painter = QPainter(boxed)
    painter.fillRect(280, 0, 720, 720, QColor("#d0b090"))  # квадрат обложки
    painter.end()
    assert crop_side_bars(boxed).size() == QSize(720, 720)

    plain = QImage(1280, 720, QImage.Format.Format_RGB32)
    plain.fill(QColor("#205060"))  # обычный кадр клипа — не трогаем
    assert crop_side_bars(plain).size() == QSize(1280, 720)


def _shown(layer: PlaylistArtLayer) -> bool:
    layer._fade.setCurrentTime(layer._fade.duration())
    return layer.isVisible()


def test_layer_takes_track_cover_in_full_size(qapp, tmp_path) -> None:
    from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor

    comp = BackdropCompositor()
    comp.set_mode("cover")
    layer = PlaylistArtLayer()
    layer.resize(640, 360)
    layer.bind_backdrop(comp)
    layer.set_shown(True)
    small = QImage(96, 96, QImage.Format.Format_RGB32)
    small.fill(QColor("white"))
    comp.set_cover(small, _save(tmp_path / "cover.png", 1200, 1200))
    assert layer._art.width() == 1200  # не растянутые 96 px из фона
    comp.set_cover(None)
    assert comp.cover_path() is None


def test_layer_follows_backdrop_mode_and_track_cover(qapp) -> None:
    from quantis.ui.views.widgets.backdrop_compositor import BackdropCompositor

    comp = BackdropCompositor()
    comp.set_size(QSize(640, 360))
    layer = PlaylistArtLayer()
    layer.resize(640, 360)
    layer.set_art(None, "Микс дня")
    layer.bind_backdrop(comp)
    layer.set_shown(True)

    comp.set_mode("palette")  # «Цвета трека»: фон остаётся как есть
    assert not _shown(layer)

    comp.set_mode("cover")
    assert _shown(layer)
    own = layer.grab().toImage().pixelColor(600, 180)
    cover = QImage(96, 96, QImage.Format.Format_RGB32)
    cover.fill(QColor("#20e040"))
    comp.set_cover(cover)  # заиграл трек — арт теперь его обложка
    assert not comp.needs_drift()  # под артом обложке плыть незачем
    shown = layer.grab().toImage().pixelColor(600, 180)
    assert shown != own and shown.green() > shown.red() + 80

    # клип пошёл — арт его не заслоняет
    comp.set_mode("video")
    assert _shown(layer)
    comp.set_video_frame(cover)
    comp.set_video_active(True)
    assert not _shown(layer)

    comp.set_mode("cover")
    layer.set_shown(False)
    assert not _shown(layer)
    assert comp.needs_drift()
