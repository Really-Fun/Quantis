"""Загрузка и отрисовка обложек треков и плейлистов."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QImage,
    QImageReader,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPixmap,
)

from quantis.models.track import Track
from quantis.providers.path_provider import PathProvider
from quantis.services.cover_validate import cover_file_ok
from quantis.ui.design_tokens import BADGE_SOUNDCLOUD, BADGE_YANDEX, BADGE_YOUTUBE
from quantis.ui.fonts import app_font

_GRAD_YT = (QColor(BADGE_YOUTUBE), QColor(140, 30, 30))
_GRAD_YA = (QColor(BADGE_YANDEX), QColor(180, 140, 20))
_GRAD_SC = (QColor(BADGE_SOUNDCLOUD), QColor(140, 70, 0))

# Общий LRU: ключ "(path|track)|size" → pixmap. Ограничивает рост ОЗУ.
_COVER_CACHE_MAX = 64
_cover_lru: OrderedDict[str, QPixmap | None] = OrderedDict()


def gradient_for_name(name: str) -> tuple[QColor, QColor]:
    seed = sum(ord(ch) for ch in name) or 1
    hues = [
        (0, 229, 255),
        (230, 59, 46),
        (255, 42, 127),
        (120, 90, 255),
        (255, 170, 0),
        (46, 204, 113),
        (155, 89, 182),
    ]
    a = hues[seed % len(hues)]
    b = hues[(seed * 3 + 2) % len(hues)]
    return QColor(*a), QColor(*b)


def track_cover_file(track: Track) -> Path:
    return Path(PathProvider().get_cover_path(track))


def clear_cover_cache() -> None:
    _cover_lru.clear()


def invalidate_cover_path(path: str | Path | None) -> None:
    if not path:
        return
    prefix = str(Path(path).resolve() if Path(path).exists() else Path(path))
    dead = [key for key in _cover_lru if key.startswith(prefix)]
    for key in dead:
        _cover_lru.pop(key, None)


def playlist_cover_path(playlist) -> str | None:
    """Обложка плейлиста: своя → иначе обложка первого трека."""
    cover = getattr(playlist, "cover_path", None)
    if cover:
        path = Path(cover)
        if path.is_file() or path.suffix.lower() == ".svg":
            return str(path)
    tracks = getattr(getattr(playlist, "tracks", None), "values", None)
    if tracks:
        return str(track_cover_file(tracks[0]))
    return cover


def _cache_get(key: str) -> QPixmap | None | object:
    """Возвращает pixmap / None / sentinel object если ключа нет."""
    if key not in _cover_lru:
        return _MISSING
    _cover_lru.move_to_end(key)
    return _cover_lru[key]


_MISSING = object()


def _cache_put(key: str, value: QPixmap | None) -> QPixmap | None:
    _cover_lru[key] = value
    _cover_lru.move_to_end(key)
    while len(_cover_lru) > _COVER_CACHE_MAX:
        _cover_lru.popitem(last=False)
    return value


def _crop_letterbox(image: QImage) -> QImage:
    """YouTube hq/sd default — 4:3 рамка с 16:9 картинкой и чёрными полями."""
    width, height = image.width(), image.height()
    if width < 16 or height < 16:
        return image
    ratio = width / height
    if not 1.28 <= ratio <= 1.40:
        return image
    bar = max(1, round(height * 45 / 360))
    inner = height - 2 * bar
    if inner <= height * 0.5:
        return image
    return image.copy(0, bar, width, inner)


def _cover_key(file_path: Path, size: int) -> str:
    return f"{file_path.resolve() if file_path.exists() else file_path}|{size}"


def _decode_cover(file_path: Path, size: int) -> QImage | None:
    """Декодирует обложку целиком и режет в квадрат по центру. Без QPixmap —
    можно звать из пула потоков."""
    if not file_path.is_file() or not cover_file_ok(file_path):
        return None
    reader = QImageReader(str(file_path))
    reader.setAutoTransform(True)
    # setScaledSize на JPEG в Qt часто работает как clip с (0,0) — в UI
    # остаётся только верхняя полоса обложки. Файлы обложек маленькие.
    image = reader.read()
    if image.isNull():
        return None
    image = _crop_letterbox(image)
    if image.format() != QImage.Format.Format_RGB32:
        image = image.convertToFormat(QImage.Format.Format_RGB32)
    if image.width() != size or image.height() != size:
        image = image.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (image.width() - size) // 2)
        y = max(0, (image.height() - size) // 2)
        image = image.copy(x, y, size, size)
    return image


def load_cover_pixmap(path: str | Path | None, size: int) -> QPixmap | None:
    """Обложка квадратом ``size`` (декодирует сразу, в вызывающем потоке)."""
    if not path:
        return None
    file_path = Path(path)
    cache_key = _cover_key(file_path, size)
    cached = _cache_get(cache_key)
    if cached is not _MISSING:
        return cached  # type: ignore[return-value]
    if file_path.suffix.lower() == ".svg":
        return _cache_put(cache_key, _svg_pixmap(file_path, size))
    image = _decode_cover(file_path, size)
    return _cache_put(cache_key, None if image is None else QPixmap.fromImage(image))


def _svg_pixmap(file_path: Path, size: int) -> QPixmap | None:
    if not file_path.is_file():
        return None
    pixmap = QIcon(str(file_path)).pixmap(QSize(size, size))
    return None if pixmap.isNull() else pixmap


class _DecodeJob(QRunnable):
    def __init__(self, decoder: CoverDecoder, key: str, path: Path, size: int) -> None:
        super().__init__()
        self._decoder, self._key, self._path, self._size = decoder, key, path, size

    def run(self) -> None:
        try:
            image = _decode_cover(self._path, self._size)
        except Exception:
            image = None
        self._decoder._decoded.emit(self._key, image if image is not None else QImage())


class CoverDecoder(QObject):
    """Обложки для списков: декодируются в пуле потоков, а не в paint().
    Пока обложки нет, делегат рисует заглушку; ``ready`` — пора перерисовать."""

    ready = Signal()
    _decoded = Signal(str, QImage)
    _instance: CoverDecoder | None = None

    def __init__(self) -> None:
        super().__init__()
        self._pending: set[str] = set()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._decoded.connect(self._on_decoded)
        self._notify = QTimer(self)  # пачка обложек → одна перерисовка
        self._notify.setSingleShot(True)
        self._notify.setInterval(16)
        self._notify.timeout.connect(self.ready.emit)

    @classmethod
    def instance(cls) -> CoverDecoder:
        if cls._instance is None:
            cls._instance = CoverDecoder()
        return cls._instance

    def request(self, path: str | Path | None, size: int) -> QPixmap | None:
        """Из кэша; если обложки там нет — None и декодирование в фоне."""
        if not path:
            return None
        file_path = Path(path)
        key = _cover_key(file_path, size)
        cached = _cache_get(key)
        if cached is not _MISSING:
            return cached  # type: ignore[return-value]
        if file_path.suffix.lower() == ".svg":
            return _cache_put(key, _svg_pixmap(file_path, size))
        if key not in self._pending:
            self._pending.add(key)
            self._pool.start(_DecodeJob(self, key, file_path, size))
        return None

    def _on_decoded(self, key: str, image: QImage) -> None:
        self._pending.discard(key)
        _cache_put(key, None if image.isNull() else QPixmap.fromImage(image))
        self._notify.start()


def request_track_cover(track: Track, size: int) -> QPixmap | None:
    return CoverDecoder.instance().request(track_cover_file(track), size)


def load_track_cover(track: Track, size: int) -> QPixmap | None:
    return load_cover_pixmap(track_cover_file(track), size)


def load_wallpaper_pixmap(path: str | Path | None, max_side: int = 1920) -> QPixmap:
    """Декодирует обои с ограничением длинной стороны (экономия ОЗУ на 4K)."""
    if not path:
        return QPixmap()
    file_path = Path(path)
    if not file_path.is_file():
        return QPixmap()

    reader = QImageReader(str(file_path))
    reader.setAutoTransform(True)
    original = reader.size()
    if original.isValid():
        w, h = original.width(), original.height()
        longest = max(w, h)
        if longest > max_side:
            scale = max_side / longest
            reader.setScaledSize(QSize(max(1, int(w * scale)), max(1, int(h * scale))))

    image = reader.read()
    if image.isNull():
        return QPixmap()
    return QPixmap.fromImage(image)


def paint_rounded_cover(
    painter: QPainter,
    rect,
    *,
    label: str,
    pixmap: QPixmap | None = None,
    source_key: str = "",
    radius: int = 8,
    with_badge: bool = True,
) -> None:
    from quantis.ui.views.widgets.source_badge import paint_source_badge

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if pixmap is not None and not pixmap.isNull():
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(rect, pixmap)
        painter.setClipping(False)
    else:
        key = str(source_key).lower()
        if key == "youtube":
            c1, c2 = _GRAD_YT
        elif key == "yandex":
            c1, c2 = _GRAD_YA
        elif key == "soundcloud":
            c1, c2 = _GRAD_SC
        else:
            c1, c2 = gradient_for_name(label)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, c1)
        grad.setColorAt(1.0, c2)
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, radius, radius)
        initial = (label[:1] or "?").upper()
        painter.setPen(QColor(255, 255, 255, 230))
        painter.setFont(app_font(max(9, rect.width() // 4), QFont.Weight.Bold))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initial)

    if with_badge and source_key:
        paint_source_badge(painter, rect, source_key)
    painter.restore()
