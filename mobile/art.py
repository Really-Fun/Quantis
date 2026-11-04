"""Обложки, палитра из обложки и картинки для QML (image://art/…).

Обложки качает Python (HTTPS у него на телефоне уже работает) и кладёт в
кэш на диске. Провайдер рисует заранее то, что в QML пришлось бы делать
масками и шейдерами: скруглённую обложку, пластинку с обложкой на
«яблоке» и мягкие цветные пятна для авроры.

Адреса для QML:
- image://art/cover/<pct>/<url-encoded https> — квадрат, углы pct% стороны;
- image://art/vinyl/<url-encoded https>  — пластинка (url может быть пустым);
- image://art/blob/<rrggbb>              — радиальное пятно этого цвета.
"""

from __future__ import annotations

import colorsys
import hashlib
import logging
import ssl
import threading
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

from PySide6.QtCore import QPointF, QRectF, QSize, QStandardPaths, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtQuick import QQuickImageProvider

log = logging.getLogger(__name__)

_TIMEOUT = 15
_MEMORY = 48  # обложек в памяти
_lock = threading.Lock()
_images: OrderedDict[str, QImage] = OrderedDict()


def _cache_dir() -> Path:
    base = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.CacheLocation
    )
    path = Path(base or Path.home() / ".cache" / "quantis-mobile") / "covers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _ssl_context() -> ssl.SSLContext:
    import certifi  # на телефоне — свой certifi.py рядом

    return ssl.create_default_context(cafile=certifi.where() or None)


def cover_file(url: str) -> Path:
    """Файл обложки в кэше на диске (может ещё не существовать)."""
    return _cache_dir() / (hashlib.sha1(url.encode()).hexdigest() + ".img")


def load_cover(url: str) -> QImage | None:
    """Обложка из памяти, с диска или из сети; None — не удалось."""
    if not url.startswith("https://"):
        return None
    with _lock:
        cached = _images.get(url)
        if cached is not None:
            _images.move_to_end(url)
            return cached
    path = cover_file(url)
    data = path.read_bytes() if path.exists() else None
    if data is None:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Quantis"})
            with urllib.request.urlopen(
                request, timeout=_TIMEOUT, context=_ssl_context()
            ) as r:
                data = r.read()
            path.write_bytes(data)
        except Exception as exc:
            log.info("Обложка не загрузилась (%s): %s", url, exc)
            return None
    image = QImage()
    if not image.loadFromData(data) or image.isNull():
        return None
    image = _square(image)
    with _lock:
        _images[url] = image
        while len(_images) > _MEMORY:
            _images.popitem(last=False)
    return image


def _square(image: QImage) -> QImage:
    """Квадрат из центра: у превью YouTube 4:3 с чёрными полосами 16:9."""
    w, h = image.width(), image.height()
    if abs(w - h) <= 2:
        return image
    if w * 3 == h * 4:  # hqdefault 480×360: картинка 16:9 внутри
        inner_h = w * 9 // 16
        image = image.copy(0, (h - inner_h) // 2, w, inner_h)
        w, h = image.width(), image.height()
    side = min(w, h)
    return image.copy((w - side) // 2, (h - side) // 2, side, side)


# --- палитра -----------------------------------------------------------------


@dataclass(frozen=True)
class Palette:
    accent: QColor
    accent2: QColor
    deep: QColor
    accent_text: QColor
    glow: QColor  # яркий оттенок для авроры: контраст с текстом ему не нужен


DEFAULT = Palette(
    accent=QColor("#6C5CE7"),
    accent2=QColor("#FF2A7F"),
    deep=QColor("#1A1240"),
    accent_text=QColor("#FFFFFF"),
    glow=QColor("#7C6CF0"),
)


def _luminance(color: QColor) -> float:
    def channel(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * channel(color.redF())
        + 0.7152 * channel(color.greenF())
        + 0.0722 * channel(color.blueF())
    )


def _contrast(a: QColor, b: QColor) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def _hls(h: float, l: float, s: float) -> QColor:  # noqa: E741
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, s)
    return QColor.fromRgbF(r, g, b)


def palette_from(image: QImage | None) -> Palette:
    """Два ярких оттенка обложки и глубокий фон; серые обложки — Aurora.

    Яркость акцента ограничена, чтобы на нём читался текст (4,5:1).
    """
    if image is None or image.isNull():
        return DEFAULT
    small = image.scaled(
        24,
        24,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    buckets: dict[int, float] = {}
    for y in range(small.height()):
        for x in range(small.width()):
            c = small.pixelColor(x, y)
            h, l, s = colorsys.rgb_to_hls(c.redF(), c.greenF(), c.blueF())  # noqa: E741
            weight = s * (
                1 - abs(l - 0.5) * 2
            )  # насыщенные и не слишком тёмные/светлые
            if weight > 0.08:
                key = int(h * 18) % 18  # корзины по 20°
                buckets[key] = buckets.get(key, 0) + weight
    if not buckets:
        return DEFAULT
    ranked = sorted(buckets, key=buckets.get, reverse=True)
    first = ranked[0]
    second = next(
        (k for k in ranked[1:] if min(abs(k - first), 18 - abs(k - first)) >= 2), None
    )
    h1 = (first + 0.5) / 18
    h2 = (second + 0.5) / 18 if second is not None else h1 + 0.11
    # На акценте всегда белые текст и значки: темним акцент до 4,5:1.
    white = QColor("#FFFFFF")
    lightness = 0.58
    accent = _hls(h1, lightness, 0.72)
    while _contrast(accent, white) < 4.5 and lightness > 0.2:
        lightness -= 0.03
        accent = _hls(h1, lightness, 0.72)
    accent2 = _hls(h2, 0.55, 0.78)
    deep = _hls(h1, 0.11, 0.55)
    glow = _hls(h1, 0.56, 0.8)
    return Palette(
        accent=accent, accent2=accent2, deep=deep, accent_text=white, glow=glow
    )


# --- картинки для QML --------------------------------------------------------


def _rounded(image: QImage, side: int, radius_ratio: float) -> QImage:
    out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    clip = QPainterPath()
    r = side * radius_ratio
    clip.addRoundedRect(QRectF(0, 0, side, side), r, r)
    p.setClipPath(clip)
    p.drawImage(QRectF(0, 0, side, side), image)
    p.end()
    return out


def _vinyl(label: QImage | None, side: int) -> QImage:
    """Пластинка: чёрный диск с бороздками, бликом и обложкой в центре."""
    out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    c = side / 2
    p.setPen(Qt.PenStyle.NoPen)
    body = QRadialGradient(QPointF(c, c), c)
    body.setColorAt(0, QColor("#1E1E26"))
    body.setColorAt(0.7, QColor("#15151B"))
    body.setColorAt(1, QColor("#0E0E13"))
    p.setBrush(QBrush(body))
    p.drawEllipse(QPointF(c, c), c, c)
    # Ободок: край диска виден и на тёмном фоне.
    rim = QPen(QColor(255, 255, 255, 46))
    rim.setWidthF(max(1.5, side / 260))
    p.setPen(rim)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(c, c), c - rim.widthF(), c - rim.widthF())
    # Бороздки: тонкие кольца чуть светлее диска.
    groove = QPen(QColor(255, 255, 255, 20))
    groove.setWidthF(max(1.0, side / 600))
    p.setPen(groove)
    p.setBrush(Qt.BrushStyle.NoBrush)
    ring = c * 0.96
    while ring > c * 0.36:
        p.drawEllipse(QPointF(c, c), ring, ring)
        ring -= side / 110
    # Блик: вращается вместе с диском — так видно, что пластинка крутится.
    p.setPen(Qt.PenStyle.NoPen)
    # Два блика напротив друг друга — по ним видно вращение.
    for sx, sy in ((0.55, 0.45), (1.45, 1.55)):
        shine = QRadialGradient(QPointF(c * sx, c * sy), c * 0.75)
        shine.setColorAt(0, QColor(255, 255, 255, 52))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(shine))
        p.drawEllipse(QPointF(c, c), c * 0.97, c * 0.97)
    # «Яблоко» с обложкой и отверстие.
    label_r = c * 0.34
    clip = QPainterPath()
    clip.addEllipse(QPointF(c, c), label_r, label_r)
    if label is not None and not label.isNull():
        p.save()
        p.setClipPath(clip)
        p.drawImage(QRectF(c - label_r, c - label_r, 2 * label_r, 2 * label_r), label)
        p.restore()
    else:
        p.setBrush(QColor("#7C6CF0"))
        p.drawEllipse(QPointF(c, c), label_r, label_r)
    p.setBrush(QColor("#0B0D12"))
    p.drawEllipse(QPointF(c, c), side * 0.018, side * 0.018)
    p.end()
    return out


def _blob(color: QColor, side: int) -> QImage:
    out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    gradient = QRadialGradient(QPointF(side / 2, side / 2), side / 2)
    for stop, alpha in ((0, 235), (0.4, 130), (0.75, 35), (1, 0)):
        tinted = QColor(color)
        tinted.setAlpha(alpha)
        gradient.setColorAt(stop, tinted)
    p.fillRect(out.rect(), QBrush(gradient))
    p.end()
    return out


class ArtProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, id: str, size: QSize, requested: QSize) -> QImage:  # noqa: A002
        kind, _, rest = id.partition("/")
        side = max(requested.width(), requested.height(), 0) or 512
        side = min(side, 1024)
        if kind == "blob":
            return _blob(QColor("#" + rest[:6]), min(side, 256))
        round_pct = 8
        if kind == "cover":
            pct, _, rest = rest.partition("/")
            round_pct = int(pct) if pct.isdigit() else 8
        cover = load_cover(unquote(rest)) if rest else None
        if kind == "vinyl":
            return _vinyl(cover, side)
        if cover is None:
            return QImage()  # QML покажет запасной градиент
        return _rounded(cover, side, min(round_pct, 50) / 100)
