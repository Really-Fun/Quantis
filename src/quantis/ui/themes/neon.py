"""Aurora — тема по умолчанию: графит и свечение цвета обложки."""

from quantis.ui.themes.spec import (
    BackdropSpec,
    GlowSpec,
    ThemeColors,
    ThemeFonts,
    ThemeSpec,
)

UI_FONTS = ("Bahnschrift", "Segoe UI Variable Display", "Segoe UI", "sans-serif")
MONO_FONTS = ("Cascadia Mono", "Consolas", "Bahnschrift", "monospace")

DARK_DEPTH = (
    (0.0, "rgba(20, 28, 48, 40)"),
    (0.55, "rgba(0, 0, 0, 0)"),
    (1.0, "rgba(0, 0, 0, 110)"),
)

EXTRA_QSS = """
#headerGreeting {
    letter-spacing: 0.15px;
}

#seekSlider::handle:horizontal:hover {
    border-color: #ffffff;
}

QScrollBar::handle:vertical {
    background: rgba(108, 92, 231, 0.55);
    min-height: 48px;
}

#searchInput {
    border-radius: 14px;
    padding: 13px 16px;
    selection-background-color: rgba(108, 92, 231, 0.35);
}

QFrame#glassPanel {
    border: 1px solid rgba(255, 255, 255, 0.06);
}

QToolButton#sourceFilterChip {
    color: #8A92A6;
}

QToolButton#sourceFilterChip:checked {
    color: #F2F4F8;
}

#pluginCardDesc {
    color: #8A92A6;
}

QToolButton#navPinButton {
    color: #8A92A6;
}

QToolButton#navPinButton:checked {
    border-color: rgba(108, 92, 231, 0.45);
    color: #F2F4F8;
}

QToolButton#advancedToggle:checked {
    border-color: rgba(255, 255, 255, 0.28);
}

#searchStatus {
    min-height: 16px;
}

QFrame#sideNavRail[expanded="true"] {
    border: 1px solid rgba(108, 92, 231, 0.22);
}

QToolButton#navIconButton:hover {
    color: #F2F4F8;
}

QToolButton#navIconButton:checked {
    color: #F2F4F8;
}

QToolButton#navIconButton[plugin="true"] {
    border: 1px solid rgba(138, 146, 166, 0.22);
}

#controlButton[plugin="true"] {
    border: 1px solid rgba(138, 146, 166, 0.35);
}
"""

THEME = ThemeSpec(
    id="neon",
    label="Aurora",
    mode="dark",
    order=10,
    aliases=("aurora",),
    colors=ThemeColors(
        bg="#0B0D12",
        ink_rgb="255, 255, 255",
        mist_rgb="226, 232, 240",
        text="#F2F4F8",
        title="#f8fafc",
        text_dim="#8A92A6",
        text_meta="#8A92A6",
        text_soft="#e2e8f0",
        tint="#6C5CE7",
        tint_rgb="108, 92, 231",
        tint_hover="#7F71F0",
        on_tint="#F2F4F8",
        hl_rgb="46, 230, 255",
        accent_fallback="#6C5CE7",
        surface="rgba(20, 24, 33, 0.92)",
        chip_bg="rgba(255, 255, 255, 0.04)",
        field_bg="rgba(0, 0, 0, 0.4)",
        handle="#ffffff",
        popup_bg="rgba(10, 12, 20, 220)",
        popup_border="2px solid rgba(0, 220, 255, 150)",
        list_bg="#0b0d16",
    ),
    fonts=ThemeFonts(ui=UI_FONTS, display=UI_FONTS, mono=MONO_FONTS),
    backdrop=BackdropSpec(depth=DARK_DEPTH, glow=GlowSpec("cover")),
    radius=16,
    radius_control=12,
    wallpaper_opacity=0.11,
    extra_qss=EXTRA_QSS,
)
