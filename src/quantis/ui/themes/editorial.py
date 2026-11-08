"""Редакционная — журнальная вёрстка: засечки, моноширинные метки, прямые углы.

Один акцент — красная «плашка» (#E63B2E) на чёрном и «бумажном» тексте:
цвет обложки интерфейс не перекрашивает, свечений и градиентов нет.
"""

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
    background: rgba(${mist_rgb}, 0.35);
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
    color: ${tint};
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
#controlButton[compact="true"],
#seekSlider::groove:horizontal,
#volSlider::groove:horizontal,
#seekSlider::handle:horizontal,
#volSlider::handle:horizontal,
QFrame#glassPanel {
    border-radius: 0;
}

#seekSlider::handle:horizontal:hover {
    background: ${tint_hover};
}

#volSlider::sub-page:horizontal {
    background: ${tint};
}

#searchInput {
    border: none;
    border-radius: 0;
    selection-background-color: rgba(${tint_rgb}, 0.45);
}

QFrame#PlayMenu {
    border-radius: 0;
    border-top: 2px solid ${tint};
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
        hl_rgb="230, 59, 46",
        accent_fallback="#E63B2E",
        surface="transparent",
        chip_bg="rgba(255, 255, 255, 0.04)",
        field_bg="rgba(0, 0, 0, 0.4)",
        handle="#f2f0eb",
        popup_bg="rgba(12, 12, 14, 245)",
        popup_border="1px solid rgba(242, 240, 235, 0.22)",
        list_bg="#0A0A0C",
    ),
    fonts=ThemeFonts(ui=SERIF, display=SERIF, mono=MONO, label=MONO),
    backdrop=BackdropSpec(depth=DARK_DEPTH, vignette=None, glow=None),
    radius=0,
    glass_blur=0,  # журнальные панели: сплошные, без стекла
    radius_control=0,
    card_style="magazine",
    fixed_accent=True,
    extra_qss=EXTRA_QSS,
)
