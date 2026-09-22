from __future__ import annotations

from pathlib import Path

from quantis.services.cover_validate import cover_bytes_ok, cover_file_ok


def test_cover_bytes_reject_truncated_jpeg() -> None:
    # SOI есть, EOI нет — типичный обрезанный hqdefault.
    data = b"\xff\xd8\xff\xe0" + b"\x00" * 4000
    assert cover_bytes_ok(data) is False


def test_cover_bytes_accept_complete_jpeg() -> None:
    data = b"\xff\xd8\xff\xe0" + b"\x11" * 4000 + b"\xff\xd9"
    assert cover_bytes_ok(data) is True


def test_cover_bytes_reject_tiny_placeholder() -> None:
    data = b"\xff\xd8\xff\xe0" + b"\x11" * 2000 + b"\xff\xd9"
    assert cover_bytes_ok(data) is False


def test_cover_file_ok_svg(tmp_path: Path) -> None:
    path = tmp_path / "icon.svg"
    path.write_text("<svg></svg>")
    assert cover_file_ok(path) is True


def test_cover_file_ok_truncated(tmp_path: Path) -> None:
    path = tmp_path / "bad.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 4000)
    assert cover_file_ok(path) is False
