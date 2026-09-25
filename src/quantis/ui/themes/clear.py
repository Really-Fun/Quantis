"""Прозрачная — интерфейс почти без подложек: фон окна виден сквозь всё.

Панели — чистое стекло с лёгким размытием и едва заметной тонировкой,
поверхности и поля — на низкой непрозрачности. Меню и выпадающие списки
плотнее: поверх картинки их иначе не прочитать.
"""

from quantis.ui.themes.neon import AURORA_DISPLAY_FONTS, AURORA_UI_FONTS, MONO_FONTS
from quantis.ui.themes.spec import (
    BackdropSpec,
    GlowSpec,
    ThemeColors,
    ThemeFonts,
    ThemeSpec,
)

EXTRA_QSS = """
QScrollBar::handle:vertical {
    background: rgba(${ink_rgb}, 0.28);
    min-height: 48px;
}

#searchInput {
    border-radius: 16px;
    padding: 13px 16px;
    selection-background-color: rgba(${tint_rgb}, 0.35);
}

QFrame#glassPanel {
    border: 1px solid rgba(${ink_rgb}, 0.10);
}

QFrame#nowPlayingPanel {
    border: 1px solid rgba(${ink_rgb}, 0.10);
}

QFrame#sideNavRail {
    border: 1px solid rgba(${ink_rgb}, 0.10);
}

QFrame#PlayMenu {
    border: 1px solid rgba(${ink_rgb}, 0.12);
}
"""

THEME = ThemeSpec(
    id="clear",
    label="Прозрачная",
    mode="dark",
    order=25,
    colors=ThemeColors(
        bg="#0A0C12",
        ink_rgb="255, 255, 255",
        mist_rgb="236, 240, 248",
        text="#FFFFFF",
        title="#FFFFFF",
        text_dim="rgba(255, 255, 255, 0.72)",
        text_meta="rgba(255, 255, 255, 0.62)",
        text_soft="#EEF2F8",
        tint="#8FD3FF",
        tint_rgb="143, 211, 255",
        tint_hover="#A8DDFF",
        on_tint="#0A0C12",
        hl_rgb="170, 225, 255",
        accent_fallback="#8FD3FF",
        surface="rgba(255, 255, 255, 0.05)",
        chip_bg="rgba(255, 255, 255, 0.06)",
        field_bg="rgba(255, 255, 255, 0.07)",
        handle="#ffffff",
        popup_bg="rgba(14, 16, 24, 225)",
        popup_border="1px solid rgba(255, 255, 255, 40)",
        list_bg="rgba(14, 16, 24, 235)",
    ),
    fonts=ThemeFonts(ui=AURORA_UI_FONTS, display=AURORA_DISPLAY_FONTS, mono=MONO_FONTS),
    # Подложки почти нет, поэтому фон окна делает всю работу: цвета трека
    # плывут, а виньетка слабая — окно не темнеет к краям.
    backdrop=BackdropSpec(
        depth=((0.0, "rgba(0, 0, 0, 0)"), (1.0, "rgba(0, 0, 0, 60)")),
        vignette="rgba(0, 0, 0, 90)",
        glow=GlowSpec("cover"),
    ),
    radius=20,
    radius_control=14,
    glass_blur=0.12,
    glass_tint="rgba(255, 255, 255, 0.04)",
    extra_qss=EXTRA_QSS,
)
