"""Описание темы Quantis: всё, чем темы отличаются друг от друга, — в одном месте.

Цвета — строки в синтаксисе QSS (``#RRGGBB``, ``rgba(r, g, b, a)``) или тройки
``"r, g, b"`` (поля ``*_rgb``) для ``rgba(${ink_rgb}, 0.08)`` в шаблонах.
Все поля ``ThemeColors`` и ``ThemeFonts`` доступны в QSS-шаблонах как ``${имя}``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from typing import Literal

from PySide6.QtGui import QColor

ThemeMode = Literal["dark", "light"]
CardStyle = Literal["default", "magazine"]


@dataclass(frozen=True)
class ThemeColors:
    # --- база ---
    bg: str
    """Сплошной фон окна (под градиентами и обоями)."""
    ink_rgb: str
    """Цвет «чернил» для полупрозрачных наложений: белый в тёмных темах, тёмный в светлых."""
    mist_rgb: str
    """Мягкий текст главной (подписи, счётчики) — тройка для rgba(..., альфа)."""
    # --- текст ---
    text: str
    title: str
    """Крупные заголовки и названия."""
    text_dim: str
    """Вторичный текст: исполнитель, заголовки колонок."""
    text_meta: str
    """Мелкий служебный текст: время, статусы."""
    text_soft: str
    """Текст кнопок-«призраков»."""
    # --- цвет темы ---
    tint: str
    """Собственный цвет темы (не зависит от обложки): чипы, фокус, кнопки."""
    tint_rgb: str
    tint_hover: str
    on_tint: str
    """Текст на заливке ``tint``."""
    hl_rgb: str
    """Подсветка: кикеры, заголовки разделов, чекбоксы, ссылки-действия."""
    accent_fallback: str
    """Акцент, пока нет обложки; дальше акцент берётся из обложки."""
    # --- поверхности ---
    surface: str
    """Панели: плеер, «Сейчас играет», боковое меню."""
    chip_bg: str
    field_bg: str
    handle: str
    """Ручки ползунков."""
    # --- всплывающие окна (меню, диалоги, списки комбобоксов) ---
    popup_bg: str
    popup_border: str
    list_bg: str


@dataclass(frozen=True)
class ThemeFonts:
    """Списки семейств с запасными: победит первое установленное.
    Последним элементом — родовое семейство (``sans-serif``, ``serif``, ``monospace``).
    """

    ui: tuple[str, ...]
    display: tuple[str, ...]
    """Крупные заголовки."""
    mono: tuple[str, ...]
    """Время, технические подписи."""
    label: tuple[str, ...] = ()
    """Мелкие подписи-метки; пусто — как ``ui``."""

    def families(self, role: str) -> tuple[str, ...]:
        found: tuple[str, ...] = getattr(self, role)
        return found or self.ui

    def css(self, role: str) -> str:
        return ", ".join(
            f'"{f}"' if f not in _GENERIC else f for f in self.families(role)
        )


_GENERIC = frozenset({"sans-serif", "serif", "monospace"})


@dataclass(frozen=True)
class GlowSpot:
    """Неподвижное пятно света: координаты и радиус — доли ширины/высоты окна."""

    x: float
    y: float
    radius: float
    rgb: str
    alpha: int
    pulse_alpha: int = 0
    """Сколько добавляет пульсация (0..pulse_alpha по синусу)."""
    phase: float = 0.0


@dataclass(frozen=True)
class GlowSpec:
    """Свечение фона. ``cover`` — два пятна цвета обложки плывут по окну;
    ``spots`` — неподвижные пятна своих цветов, только дышат."""

    style: Literal["cover", "spots"]
    spots: tuple[GlowSpot, ...] = ()


@dataclass(frozen=True)
class BackdropSpec:
    """Фон окна под интерфейсом (``BackgroundFrame``)."""

    depth: tuple[tuple[float, str], ...]
    """Вертикальный градиент поверх ``bg``: (позиция, цвет)."""
    vignette: str | None = "rgba(0, 0, 0, 170)"
    glow: GlowSpec | None = None


@dataclass(frozen=True)
class ThemeSpec:
    id: str
    label: str
    mode: ThemeMode
    colors: ThemeColors
    fonts: ThemeFonts
    backdrop: BackdropSpec
    radius: int = 16
    """Радиус панелей."""
    radius_control: int = 12
    """Радиус кнопок и полей."""
    wallpaper_opacity: float = 0.11
    """Непрозрачность статичных обоев; 0 — тема обои не показывает."""
    requires_wallpaper: bool = False
    """Тема задумана поверх обоев: при выборе включаем статичные обои."""
    card_style: CardStyle = "default"
    glass_blur: float = 0.35
    """Матовое стекло панелей: глубина размытия фона 0..1; 0 — стекла нет,
    панели заливаются ``surface`` из QSS."""
    glass_tint: str = ""
    """Тонировка поверх размытого фона; пусто — ``surface`` прозрачнее в 0,6 раза."""
    extra_qss: str = ""
    """QSS только этой темы (${токены} доступны). Правила с селектором из общего
    шаблона дополняют и переопределяют его свойства."""
    aliases: tuple[str, ...] = field(default=())
    """Старые id из настроек, которые ведут на эту тему."""
    order: int = 100
    """Место в выпадающем списке настроек."""

    @property
    def is_light(self) -> bool:
        return self.mode == "light"

    @property
    def has_glass(self) -> bool:
        return self.glass_blur > 0

    def glass_tint_color(self) -> QColor:
        if self.glass_tint:
            return qcolor(self.glass_tint)
        color = qcolor(self.colors.surface)
        color.setAlphaF(color.alphaF() * 0.6)
        return color

    def tokens(self) -> dict[str, str]:
        """Значения для ``string.Template`` в QSS."""
        values = {f.name: getattr(self.colors, f.name) for f in fields(self.colors)}
        values["accent_fallback_rgb"] = rgb_triple(self.colors.accent_fallback)
        for role in ("ui", "display", "mono", "label"):
            values[f"font_{role}"] = self.fonts.css(role)
        values["radius"] = f"{self.radius}px"
        # фон стеклянных панелей: стекло рисуют сами панели, QSS — только рамку
        values["panel_bg"] = "transparent" if self.has_glass else self.colors.surface
        values["radius_control"] = f"{self.radius_control}px"
        return values


_RGBA = re.compile(r"rgba?\(([^)]*)\)")


def qcolor(value: str) -> QColor:
    """QColor из цвета в синтаксисе QSS (альфа в rgba — 0..1 или 0..255)."""
    text = value.strip()
    match = _RGBA.fullmatch(text)
    if match is None:
        if "," in text:  # тройка "r, g, b"
            return QColor(*(int(p) for p in text.split(",")))
        color = QColor(text)
        return color
    parts = [p.strip() for p in match.group(1).split(",")]
    r, g, b = (int(float(p)) for p in parts[:3])
    color = QColor(r, g, b)
    if len(parts) > 3:
        raw = parts[3]
        # как в QSS: дробная альфа — 0..1, целая — 0..255
        color.setAlpha(round(float(raw) * 255) if "." in raw else int(raw))
    return color


def rgb_triple(value: str) -> str:
    color = qcolor(value)
    return f"{color.red()}, {color.green()}, {color.blue()}"
