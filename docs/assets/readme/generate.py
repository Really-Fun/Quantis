"""Генератор анимированных SVG для README.

GitHub не пускает в README ни CSS, ни JS, но SVG, подключённый через <img>,
рендерится браузером целиком: CSS-анимации и SMIL внутри файла работают.
Внешние ссылки из такого SVG заблокированы, поэтому картинки встраиваются
в base64.

Запуск из корня репозитория:
    poetry run python docs/assets/readme/generate.py
"""

from __future__ import annotations

import base64
import io
import math
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "docs" / "assets"
OUT = Path(__file__).resolve().parent

WIDTH = 1200
FONT = "'Segoe UI', Inter, 'Helvetica Neue', Ubuntu, 'Noto Sans', Arial, sans-serif"

BG = "#07080D"
CARD = "#0E1119"
TEXT = "#F2F4F8"
DIM = "#8A92A6"
CYAN = "#2EE6FF"
VIOLET = "#6C5CE7"
MAGENTA = "#FF4FD8"
PINK = "#FF5C7A"


def jpeg_data_uri(path: Path, width: int | None = None, quality: int = 84) -> str:
    image = Image.open(path).convert("RGB")
    if width and image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=quality, optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def svg(height: int, body: str, style: str = "", defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" '
        f'viewBox="0 0 {WIDTH} {height}" font-family="{FONT}">\n'
        f"<style>{style}</style>\n<defs>{defs}</defs>\n{body}\n</svg>\n"
    )


def brand_gradient(gid: str, **attrs: str) -> str:
    extra = " ".join(f'{k.replace("_", "")}="{v}"' for k, v in attrs.items())
    return (
        f'<linearGradient id="{gid}" {extra}>'
        f'<stop offset="0" stop-color="{CYAN}"/>'
        f'<stop offset=".5" stop-color="{VIOLET}"/>'
        f'<stop offset="1" stop-color="{MAGENTA}"/>'
        "</linearGradient>"
    )


# ---------------------------------------------------------------- hero


def hero() -> str:
    height = 470
    base = 400  # линия, на которой стоят столбики эквалайзера
    logo = jpeg_data_uri(ASSETS / "hero.jpg", quality=90)

    bars = []
    count, gap = 60, 5
    bar_w = (WIDTH - 120 - gap * (count - 1)) / count
    for i in range(count):
        t = i / (count - 1)
        # огибающая: выше в центре, ниже по краям, плюс «музыкальный» шум
        envelope = 0.35 + 0.65 * math.sin(math.pi * t) ** 1.4
        wobble = 0.75 + 0.25 * math.sin(i * 1.7) * math.cos(i * 0.6)
        h = 18 + 72 * envelope * wobble
        x = 60 + i * (bar_w + gap)
        duration = 0.7 + (i * 37 % 11) / 12
        delay = -((i * 53) % 17) / 10
        bars.append(
            f'<rect class="bar" x="{x:.1f}" y="{base - h:.1f}" width="{bar_w:.1f}" '
            f'height="{h:.1f}" rx="{bar_w / 2:.1f}" '
            f'style="animation-duration:{duration:.2f}s;animation-delay:{delay:.1f}s"/>'
        )

    style = """
    .glow { animation: drift 14s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: center; }
    .g2 { animation-duration: 18s; animation-delay: -6s; }
    .g3 { animation-duration: 11s; animation-delay: -3s; }
    @keyframes drift {
      0%   { transform: translate(0, 0) scale(1); opacity: .16; }
      50%  { opacity: .3; }
      100% { transform: translate(50px, -30px) scale(1.2); opacity: .2; }
    }
    .logo { mix-blend-mode: screen; animation: flicker 7s linear infinite; }
    @keyframes flicker {
      0%, 88%, 90%, 93%, 100% { opacity: 1; }
      89% { opacity: .45; }
      91% { opacity: .75; }
      92% { opacity: .35; }
    }
    .bar { fill: url(#eq); transform-box: fill-box; transform-origin: 50% 100%;
           animation-name: eq; animation-timing-function: ease-in-out;
           animation-iteration-count: infinite; animation-direction: alternate; }
    @keyframes eq { from { transform: scaleY(.18); } to { transform: scaleY(1); } }
    .grid { stroke: #ffffff; stroke-opacity: .035; }
    """
    defs = f"""
    {brand_gradient("eq", x1="60", y1="0", x2=str(WIDTH - 60), y2="0", gradientUnits="userSpaceOnUse")}
    <radialGradient id="fade" cx=".5" cy=".5" r=".55">
      <stop offset=".62" stop-color="#fff"/><stop offset="1" stop-color="#000"/>
    </radialGradient>
    <mask id="logoMask"><rect x="160" y="10" width="880" height="344" fill="url(#fade)"/></mask>
    <linearGradient id="reflFade" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <mask id="reflMask"><rect x="0" y="{base}" width="{WIDTH}" height="{height - base}" fill="url(#reflFade)"/></mask>
    <filter id="blur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="70"/></filter>
    <clipPath id="frame"><rect width="{WIDTH}" height="{height}" rx="28"/></clipPath>
    """
    grid = "".join(
        f'<line class="grid" x1="{x}" y1="0" x2="{x}" y2="{height}"/>'
        for x in range(0, WIDTH, 40)
    ) + "".join(
        f'<line class="grid" x1="0" y1="{y}" x2="{WIDTH}" y2="{y}"/>'
        for y in range(0, height, 40)
    )
    body = f"""
    <g clip-path="url(#frame)">
      <rect width="{WIDTH}" height="{height}" fill="{BG}"/>
      {grid}
      <g filter="url(#blur)">
        <circle class="glow" cx="200" cy="330" r="130" fill="{CYAN}"/>
        <circle class="glow g2" cx="1000" cy="330" r="140" fill="{MAGENTA}"/>
        <circle class="glow g3" cx="600" cy="420" r="150" fill="{VIOLET}"/>
      </g>
      <image class="logo" href="{logo}" x="160" y="10" width="880" height="344" mask="url(#logoMask)"/>
      <g id="bars">{"".join(bars)}</g>
      <g mask="url(#reflMask)" transform="translate(0 {2 * base + 6}) scale(1 -1)"><use href="#bars"/></g>
    </g>
    <rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="28" fill="none" stroke="#ffffff" stroke-opacity=".08"/>
    """
    return svg(height, body, style, defs)


# ------------------------------------------------------------ showcase

SLIDES = (
    ("home.jpg", "Главная: «Для тебя», Моя волна и плейлисты"),
    ("search.jpg", "Поиск: три сервиса в одной выдаче"),
    ("playlist.jpg", "Плейлист: треки из разных источников вместе"),
    ("glass.jpg", "Статистика на теме Glass поверх обоев"),
)


def showcase() -> str:
    cycle = 5 * len(SLIDES)
    win_w, win_x, win_y = 1080, 60, 44
    win_h = round(win_w * 769 / 1280)
    height = win_y + win_h + 104
    share = 100 / len(SLIDES)

    style = f"""
    .slide, .cap, .dot-on {{ opacity: 0; animation: show {cycle}s infinite; }}
    .slide {{ transform-box: fill-box; transform-origin: center; animation-name: kenburns; }}
    @keyframes show {{
      0% {{ opacity: 0; }} 3% {{ opacity: 1; }}
      {share:.1f}% {{ opacity: 1; }} {share + 3:.1f}% {{ opacity: 0; }} 100% {{ opacity: 0; }}
    }}
    @keyframes kenburns {{
      0% {{ opacity: 0; transform: scale(1); }} 3% {{ opacity: 1; }}
      {share:.1f}% {{ opacity: 1; }} {share + 3:.1f}% {{ opacity: 0; transform: scale(1.045); }}
      100% {{ opacity: 0; transform: scale(1.045); }}
    }}
    .cap {{ font-size: 19px; fill: {TEXT}; letter-spacing: .2px; }}
    .halo {{ animation: breathe 6s ease-in-out infinite alternate; }}
    @keyframes breathe {{ from {{ opacity: .45; }} to {{ opacity: .9; }} }}
    """
    defs = f"""
    {brand_gradient("ring", x1="0", y1="0", x2="1", y2="1")}
    <linearGradient id="spin" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{CYAN}"/><stop offset=".35" stop-color="{VIOLET}" stop-opacity=".2"/>
      <stop offset=".65" stop-color="{MAGENTA}"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".2"/>
      <animateTransform attributeName="gradientTransform" type="rotate" from="0 .5 .5" to="360 .5 .5" dur="8s" repeatCount="indefinite"/>
    </linearGradient>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="28"/></filter>
    <clipPath id="win"><rect x="{win_x}" y="{win_y}" width="{win_w}" height="{win_h}" rx="18"/></clipPath>
    """
    images = []
    captions = []
    dots = []
    for i, (name, caption) in enumerate(SLIDES):
        uri = jpeg_data_uri(ASSETS / name, width=win_w)
        delay = f"animation-delay:{i * 5}s"
        images.append(
            f'<image class="slide" style="{delay}" href="{uri}" x="{win_x}" y="{win_y}" '
            f'width="{win_w}" height="{win_h}" preserveAspectRatio="xMidYMid slice"/>'
        )
        captions.append(
            f'<text class="cap" style="{delay}" x="{WIDTH / 2}" y="{win_y + win_h + 56}" '
            f'text-anchor="middle">{caption}</text>'
        )
        dx = WIDTH / 2 + (i - (len(SLIDES) - 1) / 2) * 22
        dots.append(
            f'<circle cx="{dx}" cy="{win_y + win_h + 84}" r="4" fill="#ffffff" fill-opacity=".18"/>'
            f'<circle class="dot-on" style="{delay}" cx="{dx}" cy="{win_y + win_h + 84}" r="4" fill="url(#ring)"/>'
        )
    first = jpeg_data_uri(ASSETS / SLIDES[0][0], width=win_w)
    body = f"""
    <rect width="{WIDTH}" height="{height}" rx="28" fill="{BG}"/>
    <rect class="halo" x="{win_x}" y="{win_y}" width="{win_w}" height="{win_h}" rx="18" fill="url(#ring)" filter="url(#soft)"/>
    <g clip-path="url(#win)">
      <rect x="{win_x}" y="{win_y}" width="{win_w}" height="{win_h}" fill="{CARD}"/>
      <image href="{first}" x="{win_x}" y="{win_y}" width="{win_w}" height="{win_h}" preserveAspectRatio="xMidYMid slice"/>
      {"".join(images)}
    </g>
    <rect x="{win_x - 1.5}" y="{win_y - 1.5}" width="{win_w + 3}" height="{win_h + 3}" rx="19.5" fill="none" stroke="url(#spin)" stroke-width="3"/>
    {"".join(captions)}
    {"".join(dots)}
    <rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="28" fill="none" stroke="#ffffff" stroke-opacity=".08"/>
    """
    return svg(height, body, style, defs)


# ------------------------------------------------------------ features

# Иконки в сетке 24×24, штрихом (в духе Lucide).
ICONS = {
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20.5 20.5 16 16"/>',
    "wave": '<path d="M2 12c2.5-5 5-5 7.5 0s5 5 7.5 0 3.5-3 5-2"/><path d="M2 17c2.5-3 5-3 7.5 0s5 3 7.5 0" opacity=".55"/><path d="M2 7c2.5-3 5-3 7.5 0s5 3 7.5 0" opacity=".55"/>',
    "film": '<rect x="2.5" y="4.5" width="19" height="15" rx="3"/><path d="m10 9 5 3-5 3z"/>',
    "download": '<path d="M12 3v12"/><path d="m7 10 5 5 5-5"/><path d="M5 20h14"/>',
    "palette": '<path d="M12 21a9 9 0 1 1 9-9c0 2.5-2 3.5-3.6 3.5H15.6a1.8 1.8 0 0 0-1.3 3.1c.6.7.1 2.4-2.3 2.4z"/><circle cx="7.5" cy="11" r="1.2"/><circle cx="10.5" cy="7" r="1.2"/><circle cx="15" cy="7.5" r="1.2"/>',
    "chart": '<path d="M3 3v18h18"/><path d="M8 16v-4"/><path d="M12.5 16V8"/><path d="M17 16v-6"/>',
    "keys": '<rect x="2" y="6" width="20" height="12" rx="2.5"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    "plug": '<rect x="3" y="3" width="7.5" height="7.5" rx="2"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="2"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="2"/><path d="M17.25 14v6.5M14 17.25h6.5"/>',
}

FEATURES = (
    ("search", "Один поиск на всё", "Яндекс.Музыка, YouTube и SoundCloud в одной", "выдаче. Или просто вставь ссылку на трек."),
    ("wave", "Моя волна и радио", "«Моя волна» Яндекса и бесконечное радио", "от любого трека."),
    ("film", "Живые обои", "Клип трека играет фоном точно в такт", "со звуком, даже на часовых миксах."),
    ("download", "Офлайн", "Скачивай треки вместе с обложками", "и слушай без интернета."),
    ("palette", "Шесть тем", "Акцентный цвет подстраивается", "под обложку того, что играет."),
    ("chart", "Статистика", "Часы прослушивания, любимый исполнитель,", "самые заслушанные треки."),
    ("keys", "Клавиатура и медиа-клавиши", "Горячие клавиши, SMTC на Windows", "и MPRIS на Linux."),
    ("plug", "Плагины", "Ставятся из .zip или по ссылке и умеют", "добавлять в интерфейс свои страницы."),
)


def features() -> str:
    pad, gap, card_h = 24, 20, 150
    card_w = (WIDTH - 2 * pad - gap) / 2
    rows = math.ceil(len(FEATURES) / 2)
    height = 2 * pad + rows * card_h + (rows - 1) * gap

    style = f"""
    .card {{ fill: {CARD}; stroke: #ffffff; stroke-opacity: .07; }}
    .edge {{ fill: none; stroke: url(#ring); stroke-width: 1.5; opacity: 0;
             animation: edge 8s ease-in-out infinite; }}
    @keyframes edge {{ 0%, 100% {{ opacity: 0; }} 12%, 22% {{ opacity: .9; }} 40% {{ opacity: 0; }} }}
    .shine {{ animation: sweep 8s ease-in-out infinite; }}
    @keyframes sweep {{ 0% {{ transform: translateX(-300px); }} 35%, 100% {{ transform: translateX({card_w + 300:.0f}px); }} }}
    .badge-glow {{ animation: pulse 4s ease-in-out infinite alternate; }}
    @keyframes pulse {{ from {{ opacity: .25; }} to {{ opacity: .7; }} }}
    .icon {{ fill: none; stroke: {TEXT}; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }}
    .title {{ font-size: 23px; font-weight: 700; fill: {TEXT}; }}
    .desc {{ font-size: 16.5px; fill: {DIM}; }}
    """
    defs = [
        brand_gradient("ring", x1="0", y1="0", x2="1", y2="1"),
        '<linearGradient id="shineG" x1="0" y1="0" x2="1" y2="0">'
        '<stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#fff" stop-opacity=".07"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>',
        '<filter id="badgeBlur" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="10"/></filter>',
    ]
    cards = []
    for i, (icon, title, line1, line2) in enumerate(FEATURES):
        col, row = i % 2, i // 2
        x = pad + col * (card_w + gap)
        y = pad + row * (card_h + gap)
        delay = f"animation-delay:{(row * 2 + col) * 0.9:.1f}s"
        defs.append(
            f'<clipPath id="c{i}"><rect x="{x:.1f}" y="{y}" width="{card_w:.1f}" height="{card_h}" rx="20"/></clipPath>'
        )
        bx, by = x + 28, y + (card_h - 64) / 2
        cards.append(
            f"""
    <g>
      <rect class="card" x="{x:.1f}" y="{y}" width="{card_w:.1f}" height="{card_h}" rx="20"/>
      <g clip-path="url(#c{i})"><g transform="translate({x:.1f} {y})">
        <rect class="shine" style="{delay}" x="0" y="-40" width="220" height="{card_h + 80}" fill="url(#shineG)" transform-origin="0 0"/>
      </g></g>
      <rect class="edge" style="{delay}" x="{x:.1f}" y="{y}" width="{card_w:.1f}" height="{card_h}" rx="20"/>
      <rect class="badge-glow" style="{delay}" x="{bx}" y="{by:.1f}" width="64" height="64" rx="18" fill="url(#ring)" filter="url(#badgeBlur)"/>
      <rect x="{bx}" y="{by:.1f}" width="64" height="64" rx="18" fill="url(#ring)"/>
      <g class="icon" transform="translate({bx + 14} {by + 14:.1f}) scale(1.5)">{ICONS[icon]}</g>
      <text class="title" x="{x + 116:.1f}" y="{y + 56}">{title}</text>
      <text class="desc" x="{x + 116:.1f}" y="{y + 88}">{line1}</text>
      <text class="desc" x="{x + 116:.1f}" y="{y + 112}">{line2}</text>
    </g>"""
        )
    return svg(height, "".join(cards), style, "".join(defs))


# -------------------------------------------------------------- themes

# (название, фон, поверхность, акцент, второй акцент, текст) — из styles/themes.
THEMES = (
    ("Aurora", "#0B0D12", "#141821", "#2EE6FF", "#FF5C7A", "#F2F4F8"),
    ("Glass", "#0E1A1C", "#1A2A2E", "#00D9A3", "#1AE0B0", "#FFFFFF"),
    ("Классическая", "#10151D", "#1A2230", "#3AA8D8", "#7FC4E6", "#EEF1F5"),
    ("Редакционная", "#0C0C0E", "#18181C", "#E63B2E", "#00E5FF", "#F2F0EB"),
    ("Светлая", "#F7F8FB", "#FFFFFF", "#6C5CE7", "#7F71F0", "#1B2030"),
    ("Тёмно-жёлтая", "#12100A", "#1C140A", "#FFAA00", "#FFBE33", "#FAF6EE"),
)


def themes() -> str:
    pad, gap = 24, 16
    tile_w = (WIDTH - 2 * pad - gap * (len(THEMES) - 1)) / len(THEMES)
    tile_h = 190
    height = pad + tile_h + 64

    style = f"""
    .tile {{ animation: float 5s ease-in-out infinite alternate; }}
    @keyframes float {{ from {{ transform: translateY(4px); }} to {{ transform: translateY(-4px); }} }}
    .name {{ font-size: 17px; font-weight: 600; fill: {TEXT}; }}
    .prog {{ animation: prog 6s linear infinite; transform-box: fill-box; transform-origin: 0 50%; }}
    @keyframes prog {{ from {{ transform: scaleX(.05); }} to {{ transform: scaleX(1); }} }}
    """
    defs = []
    tiles = []
    for i, (name, bg, surface, accent, accent2, text) in enumerate(THEMES):
        x = pad + i * (tile_w + gap)
        y = pad
        delay = f"animation-delay:{-i * 0.8:.1f}s"
        defs.append(
            f'<linearGradient id="t{i}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent2}"/></linearGradient>'
            f'<filter id="tg{i}" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="14"/></filter>'
        )
        w = tile_w
        inner_x = x + 30
        tiles.append(
            f"""
    <g class="tile" style="{delay}">
      <rect x="{x + 14:.1f}" y="{y + 20}" width="{w - 28:.1f}" height="{tile_h - 30}" rx="16" fill="{accent}" opacity=".35" filter="url(#tg{i})"/>
      <rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{tile_h}" rx="16" fill="{bg}" stroke="#ffffff" stroke-opacity=".1"/>
      <path d="M{x + 16:.1f} {y} h4 v{tile_h} h-4 a16 16 0 0 1 -16 -16 v-{tile_h - 32} a16 16 0 0 1 16 -16z" fill="{surface}"/>
      <rect x="{inner_x:.1f}" y="{y + 16}" width="44" height="44" rx="9" fill="url(#t{i})"/>
      <rect x="{inner_x + 54:.1f}" y="{y + 22}" width="{w - 104:.1f}" height="9" rx="4.5" fill="{text}" opacity=".9"/>
      <rect x="{inner_x + 54:.1f}" y="{y + 40}" width="{(w - 104) * 0.6:.1f}" height="7" rx="3.5" fill="{text}" opacity=".4"/>
      {"".join(f'<rect x="{inner_x:.1f}" y="{y + 76 + k * 22}" width="{w - 46:.1f}" height="14" rx="5" fill="{surface}"/><rect x="{inner_x + 6:.1f}" y="{y + 81 + k * 22}" width="{(w - 70) * (0.75 - k * 0.15):.1f}" height="4" rx="2" fill="{text}" opacity=".45"/>' for k in range(3))}
      <rect x="{inner_x:.1f}" y="{y + tile_h - 30}" width="{w - 86:.1f}" height="4" rx="2" fill="{text}" opacity=".15"/>
      <rect class="prog" style="{delay}" x="{inner_x:.1f}" y="{y + tile_h - 30}" width="{w - 86:.1f}" height="4" rx="2" fill="url(#t{i})"/>
      <circle cx="{x + w - 30:.1f}" cy="{y + tile_h - 28}" r="14" fill="url(#t{i})"/>
      <path d="M{x + w - 34:.1f} {y + tile_h - 35} l10 7 -10 7z" fill="{bg}"/>
      <text class="name" x="{x + w / 2:.1f}" y="{y + tile_h + 38}" text-anchor="middle">{name}</text>
    </g>"""
        )
    return svg(height, "".join(tiles), style, "".join(defs))


# --------------------------------------------------------------- stats


def count_tests() -> int:
    return sum(
        len(re.findall(r"^\s*(?:async\s+)?def test_", p.read_text(encoding="utf-8"), re.M))
        for p in (ROOT / "tests").glob("test_*.py")
    )


def stats() -> str:
    items = (
        ("3", "музыкальных сервиса"),
        ("6", "тем оформления"),
        (str(count_tests()), "автотестов"),
        ("0", "рекламы и трекинга"),
    )
    pad, gap, h = 24, 16, 118
    tile_w = (WIDTH - 2 * pad - gap * (len(items) - 1)) / len(items)
    style = f"""
    .num {{ font-size: 46px; font-weight: 800; fill: url(#ring); letter-spacing: -1px; }}
    .lbl {{ font-size: 16px; fill: {DIM}; }}
    .tile {{ fill: {CARD}; stroke: #ffffff; stroke-opacity: .07; }}
    .under {{ animation: under 5s ease-in-out infinite alternate; transform-box: fill-box; transform-origin: center; }}
    @keyframes under {{ from {{ transform: scaleX(.3); opacity: .5; }} to {{ transform: scaleX(1); opacity: 1; }} }}
    """
    defs = brand_gradient("ring", x1="0", y1="0", x2="1", y2="0")
    body = []
    for i, (num, label) in enumerate(items):
        x = pad + i * (tile_w + gap)
        cx = x + tile_w / 2
        body.append(
            f'<rect class="tile" x="{x:.1f}" y="{pad / 2}" width="{tile_w:.1f}" height="{h}" rx="18"/>'
            f'<text class="num" x="{cx:.1f}" y="{pad / 2 + 60}" text-anchor="middle">{num}</text>'
            f'<text class="lbl" x="{cx:.1f}" y="{pad / 2 + 90}" text-anchor="middle">{label}</text>'
            f'<rect class="under" style="animation-delay:{-i * 1.2:.1f}s" x="{cx - 40:.1f}" y="{pad / 2 + h - 3}" width="80" height="3" rx="1.5" fill="url(#ring)"/>'
        )
    return svg(h + pad, "".join(body), style, defs)


# ------------------------------------------------------------- divider


def divider() -> str:
    height = 56
    points = []
    for x in range(0, WIDTH + 1, 8):
        t = x / WIDTH
        amp = 14 * math.sin(math.pi * t)
        points.append(f"{x},{height / 2 + amp * math.sin(x / 38):.1f}")
    path = "M" + " L".join(points)
    style = """
    .base { fill: none; stroke: url(#ring); stroke-width: 1.2; opacity: .35; }
    .pulse { fill: none; stroke: url(#ring); stroke-width: 3; stroke-linecap: round;
             stroke-dasharray: 140 2400; filter: url(#glow); animation: run 4.5s ease-in-out infinite; }
    .p2 { animation-delay: -2.25s; opacity: .6; }
    @keyframes run { from { stroke-dashoffset: 160; } to { stroke-dashoffset: -2400; } }
    """
    defs = brand_gradient("ring", x1="0", y1="0", x2="1", y2="0") + (
        '<filter id="glow" x="-10%" y="-200%" width="120%" height="500%">'
        '<feGaussianBlur stdDeviation="3" result="b"/>'
        '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>'
    )
    body = (
        f'<path class="base" d="{path}"/>'
        f'<path class="pulse" d="{path}"/>'
        f'<path class="pulse p2" d="{path}" transform="translate(0 {height}) scale(1 -1)"/>'
        f'<path class="base" d="{path}" transform="translate(0 {height}) scale(1 -1)" opacity=".15"/>'
    )
    return svg(height, body, style, defs)


def main() -> None:
    for name, build in (
        ("hero", hero),
        ("showcase", showcase),
        ("features", features),
        ("themes", themes),
        ("stats", stats),
        ("divider", divider),
    ):
        target = OUT / f"{name}.svg"
        target.write_text(build(), encoding="utf-8")
        print(f"{target.relative_to(ROOT)}: {target.stat().st_size / 1024:.0f} КБ")


if __name__ == "__main__":
    main()
