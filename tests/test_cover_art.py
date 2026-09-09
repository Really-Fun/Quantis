"""Обложка должна быть целым кадром по центру, а не верхней полосой JPEG."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QColor, QImage, QPainter

from quantis.ui.views.widgets.cover_art import (
    clear_cover_cache,
    load_cover_pixmap,
)


def _write_banded_jpeg(path: Path, width: int = 400, height: int = 400) -> None:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.fillRect(0, 0, width, height // 2, QColor(220, 30, 30))
    painter.fillRect(0, height // 2, width, height - height // 2, QColor(30, 80, 220))
    painter.end()
    assert image.save(str(path), "JPEG", 95)


def _write_letterbox_jpeg(path: Path) -> None:
    image = QImage(480, 360, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    painter.fillRect(0, 0, 480, 360, QColor(0, 0, 0))
    painter.fillRect(0, 45, 480, 270, QColor(40, 200, 90))
    painter.end()
    assert image.save(str(path), "JPEG", 95)


def test_load_cover_uses_full_image_not_top_strip(qapp, tmp_path: Path) -> None:
    path = tmp_path / "cover.jpg"
    _write_banded_jpeg(path)
    clear_cover_cache()

    pixmap = load_cover_pixmap(path, 40)
    assert pixmap is not None
    assert pixmap.width() == 40
    assert pixmap.height() == 40

    image = pixmap.toImage()
    top = image.pixelColor(20, 8)
    bottom = image.pixelColor(20, 32)
    assert top.red() > top.blue()
    assert bottom.blue() > bottom.red()


def test_load_cover_skips_truncated_jpeg(qapp, tmp_path: Path) -> None:
    path = tmp_path / "broken.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8000)
    clear_cover_cache()
    assert load_cover_pixmap(path, 40) is None


def test_load_cover_crops_youtube_letterbox(qapp, tmp_path: Path) -> None:
    path = tmp_path / "hqdefault.jpg"
    _write_letterbox_jpeg(path)
    clear_cover_cache()

    pixmap = load_cover_pixmap(path, 80)
    assert pixmap is not None
    image = pixmap.toImage()
    pixel = image.pixelColor(40, 40)
    assert pixel.green() > 120
    assert pixel.red() < 80
