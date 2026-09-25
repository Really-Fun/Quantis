"""Тёмно-жёлтая — тёплый янтарь на почти чёрном."""

from quantis.ui.themes.neon import MONO_FONTS, UI_FONTS
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

QMessageBox QPushButton {
    border: 1px solid rgba(255, 170, 0, 100);
}

QInputDialog QPushButton {
    border: 1px solid rgba(255, 170, 0, 100);
}

QMessageBox QPushButton:hover {
    background-color: rgba(255, 170, 0, 60);
}

QInputDialog QPushButton:hover {
    background-color: rgba(255, 170, 0, 60);
}

QInputDialog QComboBox {
    background-color: rgba(20, 15, 5, 80);
    border: 1px solid rgba(255, 170, 0, 80);
}

QInputDialog QComboBox QAbstractItemView {
    border: 1px solid rgba(255, 170, 0, 80);
    selection-background-color: rgba(255, 170, 0, 80);
}

#headerGreeting {
    font-size: 20px;
    font-weight: 700;
}

#sectionTitle {
    font-size: 13px;
    font-weight: 600;
    color: rgba(255, 170, 0, 0.7);
    letter-spacing: 0.5px;
}

#headerSub {
    color: rgba(255,255,255,40);
}

#trackArtist {
    color: rgba(255, 170, 0, 0.65);
}

QScrollBar::handle:vertical {
    background: rgba(255, 170, 0, 0.35);
    border-radius: 2px;
}

#trackListView QScrollBar::handle:vertical {
    background: rgba(255, 170, 0, 40);
}

#coverLabel {
    border: none;
}

#settingLineEdit {
    border: 1px solid rgba(255, 170, 0, 30);
}

#settingsScroll QScrollBar::handle:vertical {
    background: rgba(255, 170, 0, 30);
}

#searchInput {
    border: none;
    border-radius: 10px;
    selection-background-color: rgba(255, 170, 0, 80);
}

#searchInput::placeholder {
    color: rgba(255, 255, 255, 70);
}

QFrame#PlayMenu {
    border: none;
}

QFrame#sideNavRail {
    border-radius: 22px;
    border-top: 2px solid rgba(255, 170, 0, 0.35);
}

QToolButton#navPinButton {
    color: rgba(250, 246, 238, 0.7);
}

QFrame#featuredPanel {
    border-radius: 14px;
}

#TrackListPanel {
    border-radius: 16px;
}

QWidget {
    color: #f0e8d8;
}

QPushButton#searchButton {
    font-weight: 600;
    padding: 8px 16px;
}

QToolButton#navIconButton {
    padding: 8px 10px;
    color: rgba(250, 246, 238, 0.72);
}

#PlayMenu {
    border-radius: 18px;
}

#seekSlider::sub-page:horizontal:hover {
    background: rgb(255, 170, 0);
}
"""

THEME = ThemeSpec(
    id="yellow_dark",
    label="Тёмно-жёлтая",
    mode="dark",
    order=60,
    colors=ThemeColors(
        bg="#0E0A05",
        ink_rgb="255, 255, 255",
        mist_rgb="226, 232, 240",
        text="#faf6ee",
        title="#f8fafc",
        text_dim="rgba(250, 246, 238, 0.55)",
        text_meta="rgba(250, 246, 238, 0.4)",
        text_soft="#e2e8f0",
        tint="#ffaa00",
        tint_rgb="255, 170, 0",
        tint_hover="#ffbb33",
        on_tint="#faf6ee",
        hl_rgb="255, 170, 0",
        accent_fallback="#6C5CE7",
        surface="rgba(18, 14, 8, 0.85)",
        chip_bg="rgba(255, 255, 255, 0.04)",
        field_bg="rgba(0, 0, 0, 0.4)",
        handle="#faf6ee",
        popup_bg="#140f07",
        popup_border="2px solid rgba(255, 170, 0, 80)",
        list_bg="#1c140a",
    ),
    fonts=ThemeFonts(ui=UI_FONTS, display=UI_FONTS, mono=MONO_FONTS),
    backdrop=BackdropSpec(
        depth=((0.0, "rgba(40, 24, 8, 50)"), (1.0, "rgba(0, 0, 0, 90)")),
        glow=GlowSpec(
            "spots",
            spots=(
                GlowSpot(0.85, 0.05, 0.4, "255, 170, 0", alpha=26, pulse_alpha=10),
                GlowSpot(
                    0.15, 0.9, 0.35, "255, 100, 40", alpha=18, pulse_alpha=8, phase=2.1
                ),
            ),
        ),
    ),
    radius=14,
    radius_control=10,
    wallpaper_opacity=0.11,
    extra_qss=EXTRA_QSS,
)
