"""Захват PCM-данных и FFT-анализ.

Подключается к VLCEngine через audio-callbacks.
Не управляет воспроизведением — только читает аудиопоток.

Паттерн: Singleton
Single Responsibility: только захват и анализ аудио.
Dependency Inversion: зависит от VLCEngine, а не от Player.
"""

from __future__ import annotations

import ctypes
import threading
from typing import Optional, Tuple

import numpy as np

from player.engine import VLCEngine

# --- Константы ---
DEFAULT_SAMPLE_RATE: int = 44100
DEFAULT_CHANNELS: int = 2
BYTES_PER_SAMPLE: int = 2
DEFAULT_FFT_SIZE: int = 1024
MIN_FFT_SIZE: int = 32
BUFFER_DURATION_SEC: float = 2.0


class VizualPlayer:
    """Синглтон. Захватывает PCM из VLC и отдаёт FFT-спектр."""

    _instance: VizualPlayer | None = None

    def __new__(cls, *args, **kwargs) -> VizualPlayer:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        sample_rate: int = DEFAULT_SAMPLE_RATE,
        channels: int = DEFAULT_CHANNELS,
        samples_per_read: int = DEFAULT_FFT_SIZE,
    ) -> None:
        if getattr(self, "_initialized", False):
            return

        self._sample_rate = int(sample_rate)
        self._channels = int(channels)
        self._samples_per_read = int(samples_per_read)

        self._buffer = bytearray()
        self._lock = threading.Lock()

        self._engine = VLCEngine()
        self._opaque = ctypes.c_void_p(0)

        # C-callback должен жить столько же, сколько объект — сохраняем ссылку.
        self._cb_play = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int64
        )(self._play_callback)

        self._attach()
        self._initialized = True

    # --- Public API ---

    def get_fft(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """Возвращает (freqs, magnitudes) или None, если данных недостаточно."""
        buf = self._snapshot_buffer()
        if buf is None:
            return None

        samples = self._pcm_to_mono(buf)
        if samples is None or samples.size < MIN_FFT_SIZE:
            return None

        n_fft = self._pick_fft_size(samples.size)
        if n_fft is None:
            return None

        windowed = samples[-n_fft:] * np.hanning(n_fft)
        magnitudes = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / self._sample_rate)

        mag_max = magnitudes.max()
        if mag_max > 0:
            magnitudes = magnitudes / mag_max

        return freqs, magnitudes

    def clear_buffer(self) -> None:
        """Очищает внутренний буфер аудио-данных."""
        with self._lock:
            self._buffer = bytearray()

    def available_bytes(self) -> int:
        with self._lock:
            return len(self._buffer)

    def detach(self) -> None:
        """Отключает callbacks от analysis_player."""
        try:
            self._engine.analysis_player.audio_set_callbacks(
                None, None, None, None, None, self._opaque
            )
        except Exception:
            pass

    # --- VLC callback ---

    def _play_callback(self, opaque, samples_ptr, count, pts) -> None:
        """Callback от VLC: копирует блок PCM во внутренний буфер."""
        try:
            if not samples_ptr:
                return
            cnt = int(count)
            if cnt <= 0:
                return

            size_bytes = cnt * self._channels * BYTES_PER_SAMPLE
            raw = ctypes.string_at(samples_ptr, size_bytes)
            if not raw:
                return

            max_size = int(
                self._sample_rate * self._channels * BYTES_PER_SAMPLE * BUFFER_DURATION_SEC
            )
            with self._lock:
                self._buffer.extend(raw)
                if len(self._buffer) > max_size:
                    self._buffer = self._buffer[-max_size:]
        except Exception:
            pass

    # --- Internal helpers ---

    def _attach(self) -> None:
        """Регистрирует audio-callbacks на engine.analysis_player."""
        mp = self._engine.analysis_player
        try:
            mp.audio_set_format("S16N", self._sample_rate, self._channels)
        except Exception:
            pass
        try:
            mp.audio_set_callbacks(
                self._cb_play, None, None, None, None, self._opaque
            )
        except Exception:
            pass

    def _snapshot_buffer(self) -> Optional[bytes]:
        with self._lock:
            if len(self._buffer) == 0:
                return None
            return bytes(self._buffer)

    def _pcm_to_mono(self, buf: bytes) -> Optional[np.ndarray]:
        try:
            arr = np.frombuffer(buf, dtype=np.int16)
        except Exception:
            return None
        if self._channels == 2:
            if arr.size < 2:
                return None
            return arr[::2]
        return arr

    def _pick_fft_size(self, n_samples: int) -> Optional[int]:
        n_fft = min(self._samples_per_read, n_samples)
        if n_fft < MIN_FFT_SIZE:
            return None
        if n_fft % 2 != 0:
            n_fft -= 1
        return n_fft if n_fft >= MIN_FFT_SIZE else None
