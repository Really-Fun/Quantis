"""Синтез речи через edge-tts с кэшем mp3."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TTS_TIMEOUT_SEC = 4.0


def edge_tts_available() -> bool:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return False
    return True


def cache_file(root: Path, voice: str, rate: str, script: str) -> Path:
    raw = f"{voice}\n{rate}\n{script}".encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:24]
    return root / f"{digest}.mp3"


async def synthesize(
    text: str,
    dest: Path,
    *,
    voice: str,
    rate: str,
    timeout: float = TTS_TIMEOUT_SEC,
) -> Path | None:
    """Пишет mp3 в dest. None — нет пакета, ошибка или таймаут."""
    import asyncio

    try:
        import edge_tts
    except ImportError:
        logger.info("edge-tts не установлен — диктор молчит")
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest

    tmp = dest.with_suffix(".part.mp3")
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await asyncio.wait_for(communicate.save(str(tmp)), timeout=timeout)
        tmp.replace(dest)
    except Exception:
        logger.debug("edge-tts не смог озвучить реплику", exc_info=True)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    if not dest.is_file() or dest.stat().st_size <= 0:
        return None
    return dest
