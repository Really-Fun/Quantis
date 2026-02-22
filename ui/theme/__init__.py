"""Пакет общих UI-констант и стилей."""

from .colors import ACCENT, ACCENT_DIM, PANEL_DARK
from .qss import COMBO_QSS, scroll_qss
from .sizes import PANEL_RADIUS
from .visualizer import (
    AMPLITUDE,
    DECAY,
    FREQ_MAX,
    FREQ_MIN,
    GAIN,
    GLOW_LAYERS,
    MID_RATIO,
    MIN_BARS,
    REFRESH_MS_DEFAULT,
    REFRESH_MS_MAX,
    REFRESH_MS_MIN,
    SMOOTHING,
)

__all__ = [
    "ACCENT",
    "ACCENT_DIM",
    "PANEL_DARK",
    "PANEL_RADIUS",
    "COMBO_QSS",
    "scroll_qss",
    "REFRESH_MS_DEFAULT",
    "REFRESH_MS_MIN",
    "REFRESH_MS_MAX",
    "DECAY",
    "SMOOTHING",
    "MIN_BARS",
    "FREQ_MIN",
    "FREQ_MAX",
    "MID_RATIO",
    "AMPLITUDE",
    "GAIN",
    "GLOW_LAYERS",
]
