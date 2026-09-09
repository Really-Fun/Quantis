"""Отбраковка обрезанных/заглушечных обложек (JPEG без EOI и т.п.)."""

from __future__ import annotations

from pathlib import Path

_MIN_COVER_BYTES = 3500


def cover_bytes_ok(data: bytes | None) -> bool:
    """Полный JPEG/PNG/WebP, не 120×90-заглушка и не обрезанный поток."""
    if not data or len(data) < _MIN_COVER_BYTES:
        return False
    if data[:2] == b"\xff\xd8":
        return data.rstrip(b"\x00").endswith(b"\xff\xd9")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def cover_file_ok(path: str | Path | None) -> bool:
    if not path:
        return False
    file_path = Path(path)
    if not file_path.is_file():
        return False
    if file_path.suffix.lower() == ".svg":
        return file_path.stat().st_size > 0
    try:
        return cover_bytes_ok(file_path.read_bytes())
    except OSError:
        return False
