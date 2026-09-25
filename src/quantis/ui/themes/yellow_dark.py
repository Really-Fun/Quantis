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
)
