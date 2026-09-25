"""Светлая."""

from quantis.ui.themes.neon import MONO_FONTS, UI_FONTS
from quantis.ui.themes.spec import BackdropSpec, ThemeColors, ThemeFonts, ThemeSpec

THEME = ThemeSpec(
    id="light",
    label="Светлая",
    mode="light",
    order=50,
    colors=ThemeColors(
        bg="#FAFBFC",
        ink_rgb="27, 32, 48",
        mist_rgb="27, 32, 48",
        text="#1B2030",
        title="#1B2030",
        text_dim="#667085",
        text_meta="#667085",
        text_soft="#3D4555",
        tint="#6C5CE7",
        tint_rgb="108, 92, 231",
        tint_hover="#7F71F0",
        on_tint="#FFFFFF",
        hl_rgb="108, 92, 231",
        accent_fallback="#6C5CE7",
        surface="rgba(255, 255, 255, 0.82)",
        chip_bg="rgba(27, 32, 48, 0.04)",
        field_bg="rgba(255, 255, 255, 0.9)",
        handle="#FFFFFF",
        popup_bg="#F7F8FB",
        popup_border="1px solid rgba(27, 32, 48, 0.10)",
        list_bg="#FFFFFF",
    ),
    fonts=ThemeFonts(ui=UI_FONTS, display=UI_FONTS, mono=MONO_FONTS),
    backdrop=BackdropSpec(
        depth=((0.0, "rgba(255, 255, 255, 40)"), (1.0, "rgba(140, 150, 170, 50)")),
        vignette="rgba(255, 255, 255, 70)",
        glow=None,
    ),
    radius=16,
    radius_control=12,
    wallpaper_opacity=0.14,
)
