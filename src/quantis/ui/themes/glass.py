"""Glass — полупрозрачные панели поверх обоев."""

from quantis.ui.themes.neon import MONO_FONTS, UI_FONTS
from quantis.ui.themes.spec import (
    BackdropSpec,
    GlowSpec,
    ThemeColors,
    ThemeFonts,
    ThemeSpec,
)

THEME = ThemeSpec(
    id="glass",
    label="Glass",
    mode="dark",
    order=20,
    colors=ThemeColors(
        bg="#0B0D12",
        ink_rgb="255, 255, 255",
        mist_rgb="226, 232, 240",
        text="#FFFFFF",
        title="#f8fafc",
        text_dim="rgba(255, 255, 255, 0.6)",
        text_meta="rgba(255, 255, 255, 0.55)",
        text_soft="#e2e8f0",
        tint="#00D9A3",
        tint_rgb="0, 217, 163",
        tint_hover="#1AE0B0",
        on_tint="#0B0D12",
        hl_rgb="46, 230, 255",
        accent_fallback="#6C5CE7",
        surface="rgba(20, 24, 33, 0.55)",
        chip_bg="rgba(20, 24, 33, 0.4)",
        field_bg="rgba(0, 0, 0, 0.4)",
        handle="#ffffff",
        popup_bg="rgba(10, 12, 20, 220)",
        popup_border="2px solid rgba(0, 220, 255, 150)",
        list_bg="#0b0d16",
    ),
    fonts=ThemeFonts(ui=UI_FONTS, display=UI_FONTS, mono=MONO_FONTS),
    backdrop=BackdropSpec(
        depth=((0.0, "rgba(20, 24, 33, 30)"), (1.0, "rgba(0, 0, 0, 80)")),
        glow=GlowSpec("aurora"),
    ),
    radius=20,
    radius_control=14,
    wallpaper_opacity=0.10,
    requires_wallpaper=True,
)
