"""Обложки карточек «Моей волны».

Порядок: своя картинка по сиду (``assets/wave/<вид>-<значение>.jpg``) →
обложка из колеса Яндекса (фото артиста, фигура жанра) → процедурный арт
по цвету карточки. Два сида со своими картинками («Грущу в дороге» =
``mood:sad`` + ``activity:road-trip``) делят карточку по диагонали.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

from quantis.services.async_wave import WaveMood
from quantis.services.cover_validate import cover_bytes_ok
from quantis.utils import get_asset_path
from quantis.utils.app_paths import cache_dir

logger = logging.getLogger(__name__)

_ASSET_DIR = "assets/wave"
_REMOTE_SIZE = "400x400"
_MAX_REMOTE_BYTES = 4 * 1024 * 1024


# Родственные сиды без своей картинки берут картинку «родителя».
_SEED_ALIASES = {
    "genre:rock": "genre:allrock",
    "genre:rusrock": "genre:allrock",
    "genre:rusrap": "genre:rap",
    "genre:rusbards": "genre:bard",
    "genre:rusestrada": "genre:estrada",
    "genre:classical": "genre:classicalmusic",
    "genre:alternative": "genre:indie",
    "genre:lounge": "genre:jazz",
    "micro-genre:alternative-pop-rock": "genre:allrock",
    "micro-genre:pop-rock": "genre:pop",
    "micro-genre:indie-pop": "genre:indie",
}


def seed_asset_name(seed: str) -> str:
    """``diversity:reshuffle_1791…`` → ``diversity-reshuffle``."""
    seed = _SEED_ALIASES.get(seed, seed)
    kind, _, value = seed.partition(":")
    if kind == "diversity" and value.startswith("reshuffle"):
        value = "reshuffle"
    return f"{kind}-{value}".replace("/", "-")


@lru_cache(maxsize=256)
def seed_asset_path(seed: str) -> Path | None:
    """Своя картинка сида (кэш: путь спрашивается на каждой отрисовке)."""
    path = Path(get_asset_path(f"{_ASSET_DIR}/{seed_asset_name(seed)}.jpg"))
    return path if path.is_file() else None


def seed_kind(seed: str) -> str:
    return seed.partition(":")[0]


def mood_kind(mood: WaveMood) -> str:
    """Вид карточки: mood / activity / combo / genre / artist / character / control."""
    if mood.is_control:
        return "control"
    if len(mood.seeds) > 1:
        return "combo"
    kind = seed_kind(mood.seeds[0])
    if kind in ("genre", "micro-genre"):
        return "genre"
    if kind in ("diversity", "user", "local-language"):
        return "character"
    return kind


def mood_color(mood: WaveMood) -> QColor:
    """Цвет карточки: из колеса, иначе стабильный оттенок от id."""
    color = QColor(mood.color) if mood.color else QColor()
    if color.isValid() and _is_vivid(color):
        return color
    digest = hashlib.md5(mood.id.encode("utf-8")).digest()
    return QColor.fromHsv(digest[0] * 360 // 256, 170, 235)


def _is_vivid(color: QColor) -> bool:
    return color.hsvSaturation() > 60 and 70 < color.value()


class WaveArtStore(QObject):
    """Картинки карточек: свои ассеты + обложки из колеса (кэш на диске)."""

    updated = Signal()
    _instance: WaveArtStore | None = None

    def __init__(self) -> None:
        super().__init__()
        self._images: dict[str, QImage | None] = {}
        self._pending: set[str] = set()
        self._bridge = None

    @classmethod
    def instance(cls) -> WaveArtStore:
        if cls._instance is None:
            cls._instance = WaveArtStore()
        return cls._instance

    def set_bridge(self, bridge) -> None:
        self._bridge = bridge

    def seed_images(self, mood: WaveMood) -> list[QImage]:
        images = []
        for seed in mood.seeds:
            path = seed_asset_path(seed)
            if path is None:
                continue
            image = self._load(f"asset:{path}", path)
            if image is not None:
                images.append(image)
        return images[:2]

    def remote_image(self, mood: WaveMood) -> QImage | None:
        url = mood.cover_url(_REMOTE_SIZE)
        if not url:
            return None
        key = f"url:{url}"
        if key in self._images:
            return self._images[key]
        path = self._cache_path(url)
        if path.is_file():
            return self._load(key, path)
        if url not in self._pending and self._bridge is not None:
            self._pending.add(url)
            self._bridge.schedule(self._download(url, path))
        return None

    def _load(self, key: str, path: Path) -> QImage | None:
        if key in self._images:
            return self._images[key]
        image = QImage(str(path))
        self._images[key] = None if image.isNull() else image
        return self._images[key]

    @staticmethod
    def _cache_path(url: str) -> Path:
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
        return cache_dir() / "wave_art" / f"{name}.img"

    async def _download(self, url: str, path: Path) -> None:
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=20)
            headers = {"User-Agent": "Mozilla/5.0 Quantis"}
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as s:
                async with s.get(url) as response:
                    if response.status != 200:
                        return
                    expected = response.content_length
                    if expected is not None and expected > _MAX_REMOTE_BYTES:
                        return
                    data = await response.read()
            if not data or len(data) > _MAX_REMOTE_BYTES:
                return
            if expected is not None and len(data) < expected:
                return
            if not cover_bytes_ok(data):
                return
            await asyncio.to_thread(_write_file, path, data)
        except Exception:
            logger.debug("Моя волна: обложка %s", url, exc_info=True)
            return
        finally:
            self._pending.discard(url)
        if self._bridge is not None:
            self._bridge.invoke_main(self.updated.emit)


def _write_file(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def paint_wave_art(
    painter: QPainter,
    rect: QRectF,
    mood: WaveMood,
    store: WaveArtStore | None = None,
) -> None:
    """Арт карточки в ``rect`` (клип скруглением — на вызывающем)."""
    store = store or WaveArtStore.instance()
    color = mood_color(mood)
    images = store.seed_images(mood)
    if len(images) >= 2:
        _paint_split(painter, rect, images[0], images[1])
        return
    if images:
        _paint_cover(painter, rect, images[0])
        return
    remote = store.remote_image(mood)
    if remote is not None and mood_kind(mood) == "artist":
        _paint_cover(painter, rect, remote)
        _paint_tint(painter, rect, color)
        return
    paint_generative(painter, rect, mood.id, color)
    if remote is not None:
        # Фигуры жанров у Яндекса — PNG с прозрачностью: кладём поверх арта.
        inset = rect.adjusted(
            rect.width() * 0.14,
            rect.height() * 0.10,
            -rect.width() * 0.14,
            -rect.height() * 0.18,
        )
        _paint_contain(painter, inset, remote)


def _paint_cover(painter: QPainter, rect: QRectF, image: QImage) -> None:
    """Как CSS ``object-fit: cover``."""
    scale = max(rect.width() / image.width(), rect.height() / image.height())
    w, h = image.width() * scale, image.height() * scale
    target = QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)
    painter.drawImage(target, image)
    painter.restore()


def _paint_contain(painter: QPainter, rect: QRectF, image: QImage) -> None:
    scale = min(rect.width() / image.width(), rect.height() / image.height())
    w, h = image.width() * scale, image.height() * scale
    target = QRectF(rect.center().x() - w / 2, rect.center().y() - h / 2, w, h)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawImage(target, image)
    painter.restore()


def _paint_split(
    painter: QPainter, rect: QRectF, first: QImage, second: QImage
) -> None:
    """Две картинки по диагонали со светлым швом."""
    _paint_cover(painter, rect, first)
    cut = QPainterPath()
    cut.moveTo(rect.right(), rect.top() + rect.height() * 0.28)
    cut.lineTo(rect.right(), rect.bottom())
    cut.lineTo(rect.left() + rect.width() * 0.28, rect.bottom())
    cut.closeSubpath()
    painter.save()
    painter.setClipPath(cut, Qt.ClipOperation.IntersectClip)
    _paint_cover(painter, rect, second)
    painter.restore()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(255, 255, 255, 150), 1.6))
    painter.drawLine(
        QPointF(rect.right(), rect.top() + rect.height() * 0.28),
        QPointF(rect.left() + rect.width() * 0.28, rect.bottom()),
    )
    painter.restore()


def _paint_tint(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Лёгкий цветной налёт снизу — фото артиста в тон карточки."""
    grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    tint = QColor(color)
    tint.setAlpha(0)
    grad.setColorAt(0.45, tint)
    tint.setAlpha(110)
    grad.setColorAt(1.0, tint)
    painter.fillRect(rect, QBrush(grad))


def paint_generative(painter: QPainter, rect: QRectF, key: str, color: QColor) -> None:
    """Процедурный арт: тёмная база, свечение и концентрические дуги.

    Детерминирован по ``key`` — одна и та же карточка всегда одинаковая.
    """
    digest = hashlib.md5(key.encode("utf-8")).digest()
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setClipRect(rect, Qt.ClipOperation.IntersectClip)

    base = QLinearGradient(rect.topLeft(), rect.bottomRight())
    base.setColorAt(0.0, color.darker(420))
    base.setColorAt(1.0, QColor(8, 9, 14))
    painter.fillRect(rect, QBrush(base))

    second = QColor.fromHsv((color.hsvHue() + 40 + digest[1] % 60) % 360, 190, 255)
    for glow_color, fx, fy, radius in (
        (color, 0.25 + digest[2] / 512, 0.30 + digest[3] / 640, 0.75),
        (second, 0.70 + digest[4] / 1024, 0.72 + digest[5] / 1024, 0.55),
    ):
        center = QPointF(
            rect.left() + rect.width() * fx, rect.top() + rect.height() * fy
        )
        r = max(rect.width(), rect.height()) * radius
        glow = QRadialGradient(center, r)
        inner = QColor(glow_color)
        inner.setAlpha(190)
        glow.setColorAt(0.0, inner)
        inner.setAlpha(0)
        glow.setColorAt(1.0, inner)
        painter.fillRect(rect, QBrush(glow))

    # Дуги-«волны» вокруг смещённого центра
    cx = rect.left() + rect.width() * (0.35 + digest[6] / 640)
    cy = rect.top() + rect.height() * (0.40 + digest[7] / 640)
    rings = 4 + digest[8] % 3
    step = max(rect.width(), rect.height()) * 0.11
    start = digest[9] * 360 // 256
    for i in range(rings):
        r = step * (i + 1.4)
        pen_color = QColor(255, 255, 255, max(24, 120 - i * 20))
        painter.setPen(
            QPen(
                pen_color,
                1.4 + (rings - i) * 0.35,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
            )
        )
        span = 110 + (digest[10 + i] % 140)
        painter.drawArc(
            QRectF(cx - r, cy - r, 2 * r, 2 * r),
            int((start + i * 37) * 16),
            int(span * 16),
        )
    # Зерно — без него градиенты выглядят «пластиково»
    grain = _grain_image()
    painter.setOpacity(0.10)
    painter.drawTiledPixmap(rect, QPixmap.fromImage(grain))
    painter.restore()


_GRAIN: QImage | None = None


def _grain_image() -> QImage:
    global _GRAIN
    if _GRAIN is None:
        size = 96
        image = QImage(size, size, QImage.Format.Format_ARGB32)
        seed = 1234567
        for y in range(size):
            for x in range(size):
                seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
                v = seed >> 23
                image.setPixelColor(x, y, QColor(v, v, v, 255))
        _GRAIN = image
    return _GRAIN


def rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


__all__ = [
    "WaveArtStore",
    "mood_color",
    "mood_kind",
    "paint_generative",
    "paint_wave_art",
    "rounded_path",
    "seed_asset_name",
    "seed_asset_path",
    "seed_kind",
]
