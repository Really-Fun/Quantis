"""Полночь — глубокий синий и холодный ледяной акцент."""

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
QScrollBar::handle:vertical {
    background: rgba(${tint_rgb}, 0.5);
    min-height: 48px;
}

#searchInput {
    border-radius: 14px;
    padding: 13px 16px;
    selection-background-color: rgba(${tint_rgb}, 0.35);
}

QFrame#glassPanel {
    border: 1px solid rgba(${mist_rgb}, 0.07);
}

QFrame#sideNavRail[expanded="true"] {
    border: 1px solid rgba(${tint_rgb}, 0.25);
}

QToolButton#navIconButton[plugin="true"] {
    border: 1px solid rgba(${mist_rgb}, 0.2);
}
"""

THEME = ThemeSpec(
    id="midnight",
    label="Полночь",
    mode="dark",
    order=70,
    colors=ThemeColors(
        bg="#070B1A",
        ink_rgb="220, 232, 255",
        mist_rgb="190, 208, 240",
        text="#E6EEFF",
        title="#F2F6FF",
        text_dim="#8497BD",
        text_meta="#7487AD",
        text_soft="#C7D4F0",
        tint="#4FC3F7",
        tint_rgb="79, 195, 247",
        tint_hover="#6FD0FA",
        on_tint="#06101F",
        hl_rgb="128, 216, 255",
        accent_fallback="#4FC3F7",
        surface="rgba(14, 22, 48, 0.92)",
        chip_bg="rgba(120, 160, 255, 0.06)",
        field_bg="rgba(2, 6, 20, 0.5)",
        handle="#E6EEFF",
        popup_bg="rgba(8, 14, 34, 235)",
        popup_border="1px solid rgba(79, 195, 247, 90)",
        list_bg="#0A1128",
    ),
    fonts=ThemeFonts(ui=UI_FONTS, display=UI_FONTS, mono=MONO_FONTS),
    backdrop=BackdropSpec(
        depth=(
            (0.0, "rgba(20, 40, 90, 70)"),
            (0.6, "rgba(0, 0, 0, 0)"),
            (1.0, "rgba(0, 0, 10, 120)"),
        ),
        vignette="rgba(0, 0, 12, 180)",
        glow=GlowSpec(
            "spots",
            spots=(
                GlowSpot(0.85, 0.1, 0.5, "40, 90, 200", alpha=48, pulse_alpha=10),
                GlowSpot(
                    0.1, 0.9, 0.45, "79, 195, 247", alpha=22, pulse_alpha=8, phase=2.4
                ),
            ),
        ),
    ),
    radius=16,
    radius_control=12,
    wallpaper_opacity=0.08,
    extra_qss=EXTRA_QSS,
)
