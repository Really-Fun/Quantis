"""Настройки диктора: чтение и запись в QSettings плагина."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QSettings

VOICE_DMITRY = "ru-RU-DmitryNeural"
VOICE_SVETLANA = "ru-RU-SvetlanaNeural"
VOICES = (VOICE_DMITRY, VOICE_SVETLANA)

RATE_DEFAULT = "+12%"
RATES = ("+0%", "+8%", "+12%", "+20%")

DUCK_DEFAULT = 0.30
DUCK_LEVELS = (0.20, 0.30, 0.40)


def _as_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def _as_float(value, default: float, low: float, high: float) -> float:
    try:
        return max(low, min(high, float(value)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SpeakerConfig:
    enabled: bool = True
    voice: str = VOICE_DMITRY
    rate: str = RATE_DEFAULT
    duck_gain: float = DUCK_DEFAULT

    @classmethod
    def load(cls, settings: QSettings | None) -> SpeakerConfig:
        if settings is None:
            return cls()
        default = cls()
        voice = str(settings.value("voice", default.voice))
        rate = str(settings.value("rate", default.rate))
        return cls(
            enabled=_as_bool(settings.value("enabled"), default.enabled),
            voice=voice if voice in VOICES else default.voice,
            rate=rate if rate in RATES else default.rate,
            duck_gain=_as_float(
                settings.value("duck_gain"), default.duck_gain, 0.1, 0.6
            ),
        )

    def save(self, settings: QSettings | None) -> None:
        if settings is None:
            return
        settings.setValue("enabled", self.enabled)
        settings.setValue("voice", self.voice)
        settings.setValue("rate", self.rate)
        settings.setValue("duck_gain", self.duck_gain)
        settings.sync()

    def with_values(self, **kwargs) -> SpeakerConfig:
        return replace(self, **kwargs)
