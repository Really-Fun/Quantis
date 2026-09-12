"""Шкала громкости ползунка: UI 0–100 → линейная амплитуда."""

from __future__ import annotations

# Диапазон Qt LogarithmicVolumeScale: 50 дБ между тишиной и 0 дБ.
_LOG_DB_RANGE = 50.0


def ui_volume_to_linear_gain(volume: int | float) -> float:
    """Ползунок 0–100 → амплитуда 0–1 (логарифмическая шкала 50 дБ).

    ``QAudioOutput.setVolume`` и VLC ``audio_set_volume`` принимают линейную
    амплитуду. Ухо воспринимает громкость логарифмически, поэтому линейный
    ``slider/100`` звучит почти на максимуме уже около 20–30% хода.
    """
    ui = max(0.0, min(100.0, float(volume))) / 100.0
    if ui <= 0.0:
        return 0.0
    return 10.0 ** ((ui - 1.0) * (_LOG_DB_RANGE / 20.0))


def output_gain(volume: int | float, duck_gain: float = 1.0) -> float:
    """Итоговая амплитуда с учётом duck (речь поверх музыки)."""
    duck = max(0.0, min(1.0, float(duck_gain)))
    return max(0.0, min(1.0, ui_volume_to_linear_gain(volume) * duck))


def output_percent(volume: int | float, duck_gain: float = 1.0) -> int:
    """Амплитуда 0–100 для API вроде libVLC."""
    return int(round(output_gain(volume, duck_gain) * 100.0))
