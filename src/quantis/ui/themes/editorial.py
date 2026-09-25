"""Редакционная — журнальная вёрстка: засечки, моноширинные метки, прямые углы."""

from quantis.ui.themes.neon import DARK_DEPTH
from quantis.ui.themes.spec import BackdropSpec, ThemeColors, ThemeFonts, ThemeSpec

SERIF = ("Georgia", "Segoe UI", "serif")
MONO = ("Cascadia Mono", "Consolas", "monospace")

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
    radius_control=0,
    wallpaper_opacity=0.0,
    card_style="editorial",
)
