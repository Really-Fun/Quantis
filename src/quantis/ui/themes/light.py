"""Светлая."""

from quantis.ui.themes.neon import MONO_FONTS, UI_FONTS
from quantis.ui.themes.spec import BackdropSpec, ThemeColors, ThemeFonts, ThemeSpec

EXTRA_QSS = """
QMenu {
    border-radius: 16px;
}

QMessageBox {
    border-radius: 16px;
}

QDialog {
    border-radius: 16px;
}

QToolTip {
    border-radius: 16px;
}

QInputDialog {
    border-radius: 16px;
}

QMessageBox QLabel {
    color: #667085;
}

QInputDialog QLabel {
    color: #667085;
}

QMessageBox QPushButton {
    border: 1px solid rgba(${tint_rgb}, 0.28);
    border-radius: 10px;
    font-weight: 700;
}

QInputDialog QPushButton {
    border: 1px solid rgba(${tint_rgb}, 0.28);
    border-radius: 10px;
    font-weight: 700;
}

QMessageBox QPushButton:hover {
    background-color: ${tint};
    border-color: ${tint};
    color: #FFFFFF;
}

QInputDialog QPushButton:hover {
    background-color: ${tint};
    border-color: ${tint};
    color: #FFFFFF;
}

QInputDialog QComboBox {
    background-color: rgba(27, 32, 48, 0.05);
    border: 1px solid rgba(27, 32, 48, 0.10);
    border-radius: 10px;
}

QInputDialog QComboBox QAbstractItemView {
    border: 1px solid rgba(27, 32, 48, 0.10);
    selection-background-color: rgba(${tint_rgb}, 0.18);
}

#headerGreeting {
    letter-spacing: 0.15px;
}

#headerSub {
    color: #667085;
}

#playlistCount {
    color: rgba(27, 32, 48, 0.48);
}

#actionButton[accent="true"] {
    color: #FFFFFF;
}

#volSlider::handle:horizontal {
    border: 2px solid ${tint};
}

#seekSlider::handle:horizontal:hover {
    border-color: #FFFFFF;
}

QScrollBar::handle:vertical {
    background: rgba(${tint_rgb}, 0.42);
    min-height: 48px;
}

#settingLineEdit {
    border: 1px solid rgba(27, 32, 48, 0.10);
    border-radius: 10px;
}

#settingsScroll QScrollBar::handle:vertical {
    border-radius: 2px;
}

#searchInput {
    border-radius: 14px;
    padding: 13px 16px;
    selection-background-color: rgba(${tint_rgb}, 0.22);
}

#searchInput::placeholder {
    color: #98A2B3;
}

QFrame#TrackListPanel {
    border-radius: 16px;
    border-top: 1px solid rgba(${tint_rgb}, 0.14);
}

QFrame#glassPanel {
    border: 1px solid rgba(27, 32, 48, 0.08);
}

QToolButton#sourceFilterChip {
    color: #667085;
}

QToolButton#sourceFilterChip:checked {
    border-color: rgba(${tint_rgb}, 0.45);
}

#pluginCardDesc {
    color: #667085;
}

QToolButton#navPinButton {
    color: #667085;
}

QToolButton#navPinButton:checked {
    border-color: rgba(${tint_rgb}, 0.40);
}

QToolButton#advancedToggle {
    color: #667085;
    border-color: rgba(27, 32, 48, 0.12);
}

QToolButton#advancedToggle:checked {
    border-color: rgba(${tint_rgb}, 0.45);
}

QLabel#homeSectionBadge {
    color: rgba(27, 32, 48, 0.62);
}

QLabel#homePillBadge[variant="wave"] {
    color: #4C46C8;
}

QLabel#homePillBadge[variant="continue"] {
    color: #C2415A;
}

QToolButton#homeSectionAction {
    border: 1px solid rgba(27, 32, 48, 0.10);
}

QToolButton#homeSectionAction:hover {
    border-color: rgba(${tint_rgb}, 0.40);
}

QToolButton#featuredPlayBtn {
    color: #F7F8FB;
}

QToolButton#featuredPlayBtn:hover {
    color: #FFFFFF;
}

QToolButton#featuredPlayBtn:disabled {
    color: rgba(27, 32, 48, 0.32);
}

QLabel#wavePromoCount {
    color: #4C46C8;
}

QToolButton#wavePromoPlayBtn {
    color: #4C46C8;
}

QToolButton#wavePromoPlayBtn:hover {
    border-color: ${tint};
}

#searchStatus {
    min-height: 16px;
}

QLabel#settingsRowTitle {
    font-size: 14px;
}

QLabel#settingsRowDesc {
    color: #667085;
}

QCheckBox#settingsCheck {
    font-size: 13px;
    spacing: 8px;
}

QComboBox#themeCombo:hover {
    border-color: rgba(${tint_rgb}, 0.45);
}

QLineEdit#settingLineEdit:focus {
    border-color: rgba(${tint_rgb}, 0.45);
}

QComboBox#themeCombo QAbstractItemView {
    background: #FFFFFF;
    selection-background-color: rgba(${tint_rgb}, 0.16);
}

QFrame#sideNavRail[expanded="true"] {
    border: 1px solid rgba(${tint_rgb}, 0.22);
}

QToolButton#navIconButton[plugin="true"] {
    border: 1px solid rgba(102, 112, 133, 0.22);
}

#controlButton[plugin="true"] {
    border: 1px solid rgba(102, 112, 133, 0.28);
}

QFrame#settingsPanel {
    border: 1px solid rgba(27, 32, 48, 0.08);
}

QCheckBox#settingsCheck::indicator {
    border: 1px solid rgba(27, 32, 48, 0.22);
    background: rgba(255, 255, 255, 0.9);
}

QPushButton#settingsButton {
    border: 1px solid rgba(27, 32, 48, 0.10);
}

QPushButton#settingsButton:hover {
    border-color: rgba(${tint_rgb}, 0.40);
}

QPushButton#updateBannerButton {
    border: 1px solid rgba(27, 32, 48, 0.10);
}

QPushButton#updateBannerButton:hover {
    border-color: rgba(${tint_rgb}, 0.40);
}

#PlayMenu {
    border-radius: 18px;
}

#settingsScroll QScrollBar::handle:vertical:hover {
    background: rgba(${tint_rgb}, 0.55);
}
"""

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
    extra_qss=EXTRA_QSS,
)
