"""Редакционная — журнальная вёрстка: засечки, моноширинные метки, прямые углы."""

from quantis.ui.themes.neon import DARK_DEPTH
from quantis.ui.themes.spec import BackdropSpec, ThemeColors, ThemeFonts, ThemeSpec

SERIF = ("Georgia", "Noto Serif", "DejaVu Serif", "serif")
MONO = ("Cascadia Mono", "JetBrains Mono", "DejaVu Sans Mono", "monospace")

EXTRA_QSS = """
/* Журнальная вёрстка: прямые углы, тонкие начертания, метки капсом. */
QScrollBar:vertical {
    width: 3px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #00e5ff, stop:1 ${tint});
}

#playerDock {
    min-height: 0;
}

QFrame#appHeader {
    border-bottom: none;
}

#headerGreeting {
    font-size: 22px;
    font-weight: 400;
    letter-spacing: -0.2px;
}

#sectionTitle {
    font-size: 10px;
    font-weight: 500;
    color: #00e5ff;
    letter-spacing: 2px;
}

#trackTitle {
    font-size: 13px;
    font-weight: 400;
}

#trackArtist {
    font-size: 9px;
    letter-spacing: 1px;
}

#controlButton,
#seekSlider::groove:horizontal,
#volSlider::groove:horizontal,
#seekSlider::handle:horizontal,
#volSlider::handle:horizontal,
QFrame#glassPanel {
    border-radius: 0;
}

#seekSlider::handle:horizontal:hover {
    background: rgb(0, 220, 255);
}

#volSlider::sub-page:horizontal {
    background: rgba(0, 220, 255, 220);
}

#searchInput {
    border: none;
    border-radius: 0;
    selection-background-color: rgba(0, 220, 255, 120);
}

QFrame#PlayMenu {
    border-radius: 0;
    border-top: 2px solid rgba(0, 229, 255, 0.45);
}

QFrame#sideNavRail {
    border: 1px solid rgba(46, 230, 255, 0.12);
    border-radius: 0;
    border-top: 2px solid rgba(0, 229, 255, 0.4);
}

QLabel#homeGreeting {
    font-size: 34px;
    font-weight: 400;
    letter-spacing: -0.6px;
}

QLabel#homeSectionTitle {
    font-size: 24px;
    font-weight: 400;
}

QLabel#homeSectionSubtitle {
    font-size: 10px;
    letter-spacing: 1px;
    text-transform: uppercase;
}

#searchStatus {
    font-size: 10px;
    letter-spacing: 1px;
}

QToolButton#featuredPlayBtn {
    background: ${tint};
    border-radius: 0;
    color: ${on_tint};
}

QToolButton#featuredPlayBtn:hover {
    background: ${tint_hover};
    color: ${on_tint};
}

QToolButton#featuredPlayBtn:disabled {
    color: rgba(255, 255, 255, 0.35);
}

QPushButton#searchButton {
    border-radius: 0;
    font-weight: 500;
    padding: 8px 16px;
    letter-spacing: 1px;
}
"""

THEME = ThemeSpec(
    id="editorial",
    label="Редакционная",
    mode="dark",
    order=40,
    colors=ThemeColors(
        bg="#0A0A0C",
        ink_rgb="255, 255, 255",
        mist_rgb="226, 232, 240",
        text="#f2f0eb",
        title="#f2f0eb",
        text_dim="rgba(242, 240, 235, 0.45)",
        text_meta="rgba(242, 240, 235, 0.45)",
        text_soft="#e2e8f0",
        tint="#e63b2e",
        tint_rgb="230, 59, 46",
        tint_hover="#f04a3d",
        on_tint="#ffffff",
        hl_rgb="46, 230, 255",
        accent_fallback="#6C5CE7",
        surface="transparent",
        chip_bg="rgba(255, 255, 255, 0.04)",
        field_bg="rgba(0, 0, 0, 0.4)",
        handle="#f2f0eb",
        popup_bg="rgba(10, 12, 20, 220)",
        popup_border="2px solid rgba(0, 220, 255, 150)",
        list_bg="#0b0d16",
    ),
    fonts=ThemeFonts(ui=SERIF, display=SERIF, mono=MONO, label=MONO),
    backdrop=BackdropSpec(depth=DARK_DEPTH, vignette=None, glow=None),
    radius=0,
    glass_blur=0,  # журнальные панели: сплошные, без стекла
    radius_control=0,
    wallpaper_opacity=0.0,
    card_style="magazine",
    extra_qss=EXTRA_QSS,
)
