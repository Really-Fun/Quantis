import asyncio
from qasync import asyncSlot

import numpy as np
import ctypes

from vlc import Instance, MediaPlayer
from typing import Optional, Tuple
import threading

class VizualPlayer:

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        instance: Optional[Instance] = None,
        media_player: Optional[MediaPlayer] = None,
        sample_rate: int = 44100,
        channels: int = 2,
        samples_per_read: int = 1024,
    ):
        self.sample_rate = int(sample_rate)
        self.channels = int(channels)
        self.bytes_per_sample = 2
        self.samples_per_read = int(samples_per_read)

        self._buffer = bytearray()
        self._lock = threading.Lock()

        self._cb_play = None
        self._opaque = ctypes.c_void_p(0)


        if media_player is not None:
            self.player = media_player
        else:
            if instance is None:
                raise ValueError("Either 'media_player' or 'instance' must be provided")
            self.player = instance.media_player_new()

        CMPFUNC = ctypes.CFUNCTYPE(
            None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_int64
        )
        self._cb_play = CMPFUNC(self._play_callback)

        try:
            self.player.audio_set_format("S16N", self.sample_rate, self.channels)
            print("audio_set_format ok: %s Hz, %s ch", self.sample_rate, self.channels)
        except Exception as e:
            print("audio_set_format failed: %s", e)

        # Регистрируем callbacks (play, pause, resume, flush, drain, opaque)
        try:
            self.player.audio_set_callbacks(
                self._cb_play, None, None, None, None, self._opaque
            )
            print("audio callbacks registered")
        except Exception as e:
            print("audio_set_callbacks failed: %s", e)

    # Позволяет прикрепиться к другому media_player после создания
    def _attach_media_player(self, media_player: MediaPlayer):
        with self._lock:
            # Попробуем удалить callbacks от старого плеера (если возможно)
            try:
                if self.player is not None:
                    # Снять колбэки — установить None (некоторые binding-версии поддерживают)
                    try:
                        self.player.audio_set_callbacks(None, None, None, None, None, self._opaque)
                    except Exception:
                        pass
            except Exception:
                pass

            self.player = media_player
            # установить формат и callbacks на новом плеере
            try:
                self.player.audio_set_format("S16N", self.sample_rate, self.channels)
            except Exception:
                pass
            try:
                self.player.audio_set_callbacks(
                    self._cb_play, None, None, None, None, self._opaque
                )
            except Exception:
                pass

    @asyncSlot()
    async def set_media(self, some_track):
        self.player.set_media(some_track)
        await asyncio.sleep(delay=1.25)
        self.player.play()

    # --- VLC audio-play callback ---
    def _play_callback(self, opaque, samples_ptr, count, pts):
        """
        Callback от VLC: копируем указанный блок PCM в внутренний байтовый буфер.
        count — число сэмплов (frames) (по каналам).
        """
        try:
            if not samples_ptr:
                return
            cnt = int(count)
            if cnt <= 0:
                return
            size_bytes = cnt * self.channels * self.bytes_per_sample
            # безопасно читаем память
            raw = ctypes.string_at(samples_ptr, size_bytes)
            if not raw:
                return
            with self._lock:
                self._buffer.extend(raw)
                # ограничение буфера (например, 2 секунды)
                max_size = int(self.sample_rate * self.channels * self.bytes_per_sample * 2)
                if len(self._buffer) > max_size:
                    # сохраняем только последние max_size байт
                    self._buffer = self._buffer[-max_size:]
        except Exception as e:
            # В callback нельзя кидать исключения наружу — логируем
            try:
                print("Exception in audio callback: %s", e)
            except Exception:
                pass

    # --- Получение спектра ---
    def get_fft(self) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        """
        Возвращает (freqs, magnitudes) или None, если данных недостаточно.
        Работает с тем, что в буфере может быть произвольное количество байт.
        """
        with self._lock:
            if len(self._buffer) == 0:
                return None
            # копируем последние байты, чтобы не держать lock во время numpy-операций
            buf = bytes(self._buffer)

        # Конвертируем байты в int16
        try:
            arr = np.frombuffer(buf, dtype=np.int16)
        except Exception:
            return None

        # Если стерео, берём один канал (левый)
        if self.channels == 2:
            if arr.size < 2:
                return None
            samples = arr[::2]
        else:
            samples = arr

        n_samples = samples.size
        if n_samples < 32:
            # слишком мало данных для FFT
            return None

        # Выбираем длину для FFT: prefer samples_per_read, иначе ближайшее меньшее значение
        n_fft = min(self.samples_per_read, n_samples)
        # сделать n_fft чётным и >= 32
        if n_fft < 32:
            return None
        if n_fft % 2 != 0:
            n_fft -= 1
        if n_fft < 32:
            return None

        # Берём последние n_fft сэмплов
        windowed = samples[-n_fft:] * np.hanning(n_fft)

        fft_vals = np.fft.rfft(windowed)
        magnitudes = np.abs(fft_vals)

        freqs = np.fft.rfftfreq(n_fft, d=1.0 / self.sample_rate)

        # Нормализуем магнitudes (чтобы не было очень больших чисел) — optional
        mag_max = magnitudes.max()
        if mag_max > 0:
            magnitudes = magnitudes / mag_max

        return freqs, magnitudes

    def clear_buffer(self):
        """Очищает внутренний буфер аудио-данных."""
        with self._lock:
            self._buffer = bytearray()

    def detach(self):
        """Отключает callbacks от media_player (если поддерживается)."""
        try:
            if self.player is not None:
                self.player.audio_set_callbacks(None, None, None, None, None, self._opaque)
                print("audio callbacks detached")
        except Exception:
            print("Failed to detach callbacks")

    # Утилиты
    def available_bytes(self) -> int:
        with self._lock:
            return len(self._buffer)


# Пример использования (в основном модуле):
if __name__ == "__main__":
    import time

    inst = Instance()
    mp = inst.media_player_new()
    # Замените на реальный локальный файл или URL, который VLC умеет проигрывать.
    media = inst.media_new("example.mp3")  # <- path or url
    mp.set_media(media)

    viz = VizualPlayer(media_player=mp)
    print("Starting playback...")
    mp.play()
    # Даем немного времени на буферизацию и колбэки
    for i in range(100):
        time.sleep(0.1)
        res = viz.get_fft()
        if res is not None:
            freqs, mags = res
            print("FFT length:", len(freqs))
            break
    else:
        print("No FFT data received. Проверьте, что media успешно проигрывается и callback вызывается.")
    mp.stop()
    viz.detach()