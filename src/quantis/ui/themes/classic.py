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
)
