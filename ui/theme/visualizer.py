"""Константы визуализатора."""

REFRESH_MS_DEFAULT = 25
REFRESH_MS_MIN = 10
REFRESH_MS_MAX = 80

DECAY = 0.88
SMOOTHING = 0.35
MIN_BARS = 8
FREQ_MIN = 40.0
FREQ_MAX = 10000.0
MID_RATIO = 0.45
AMPLITUDE = 0.40
GAIN = 2.2

GLOW_LAYERS: list[tuple[int, float]] = [
    (12, 0.06),
    (8, 0.10),
    (5, 0.18),
    (3, 0.35),
    (1, 0.90),
]
