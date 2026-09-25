"""Классическая — сдержанный сине-серый, без свечения обложки."""

from quantis.ui.themes.neon import DARK_DEPTH, MONO_FONTS, UI_FONTS
from quantis.ui.themes.spec import (
    BackdropSpec,
    GlowSpec,
    GlowSpot,
    ThemeColors,
    ThemeFonts,
    ThemeSpec,
)

EXTRA_QSS = """
QScrollBar:vertical {
    margin: 0;
    width: 4px;
}

#playerDock {
    min-height: 0;
}

QFrame#appHeader {
    border-bottom: none;
}

#headerGreeting {
    font-size: 20px;
    font-weight: 700;
    letter-spacing: 0;
}

#sectionTitle {
    font-size: 12px;
    font-weight: 600;
    color: rgba(140, 165, 190, 0.9);
    letter-spacing: 0.8px;
}

#volSlider::handle:horizontal {
    background: #d8e4ee;
}

QScrollBar::handle:vertical {
    background: rgba(58, 168, 216, 0.4);
    border-radius: 2px;
}

#coverLabel {
    border: none;
}

#searchInput {
    border-radius: 10px;
    selection-background-color: rgba(0, 220, 255, 120);
}

QFrame#PlayMenu {
    border: none;
}

QFrame#sideNavRail {
    border: 1px solid rgba(46, 230, 255, 0.12);
    border-radius: 22px;
    border-top: 2px solid rgba(58, 168, 216, 0.35);
}

QLabel#navBrandLabel {
    color: #E8EEF5;
}

QToolButton#navPinButton {
    color: rgba(232, 238, 245, 0.7);
}

QFrame#featuredPanel {
    border-radius: 12px;
}

QWidget {
    color: #dde2e8;
}

QPushButton#searchButton {
    font-weight: 600;
    padding: 8px 16px;
}

QToolButton#navIconButton {
    padding: 8px 10px;
    color: rgba(232, 238, 245, 0.72);
}
"""

THEME = ThemeSpec(
    id="classic",
    label="Классическая",
    mode="dark",
    order=30,
    colors=ThemeColors(
        bg="#0A0C10",
        ink_rgb="255, 255, 255",
        mist_rgb="226, 232, 240",
        text="#eef1f5",
        title="#f8fafc",
        text_dim="rgba(160, 175, 195, 0.9)",
        text_meta="rgba(160, 175, 195, 0.65)",
        text_soft="#e2e8f0",
        tint="#3aa8d8",
        tint_rgb="58, 168, 216",
        tint_hover="#5bb8e0",
        on_tint="#eef1f5",
        hl_rgb="46, 230, 255",
        accent_fallback="#6C5CE7",
        surface="rgba(22, 24, 30, 0.88)",
        chip_bg="rgba(255, 255, 255, 0.04)",
        field_bg="rgba(0, 0, 0, 0.4)",
        handle="#d8e4ee",
        popup_bg="rgba(10, 12, 20, 220)",
        popup_border="2px solid rgba(0, 220, 255, 150)",
        list_bg="#0b0d16",
    ),
    fonts=ThemeFonts(ui=UI_FONTS, display=UI_FONTS, mono=MONO_FONTS),
    backdrop=BackdropSpec(
        depth=DARK_DEPTH,
        glow=GlowSpec(
            "spots",
            spots=(GlowSpot(0.7, 0.0, 0.5, "90, 130, 180", alpha=18, pulse_alpha=8),),
        ),
    ),
    radius=12,
    radius_control=10,
    wallpaper_opacity=0.12,
    extra_qss=EXTRA_QSS,
)
