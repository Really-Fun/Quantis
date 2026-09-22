"""Тесты выбора медиадвижка."""

from __future__ import annotations

from quantis.config.media_backend import backend_display_name, resolve_media_backend


def test_resolve_defaults_to_qt(monkeypatch) -> None:
    monkeypatch.delenv("QUANTIS_MEDIA_BACKEND", raising=False)
    import quantis.config.media_backend as mb

    monkeypatch.setattr(mb, "_BUILD_BACKEND", None)
    assert resolve_media_backend() == "qt"
    assert "Qt" in backend_display_name("qt")


def test_resolve_env_vlc(monkeypatch) -> None:
    monkeypatch.setenv("QUANTIS_MEDIA_BACKEND", "vlc")
    assert resolve_media_backend() == "vlc"
    assert "VLC" in backend_display_name()


def test_resolve_build_flag(monkeypatch) -> None:
    monkeypatch.delenv("QUANTIS_MEDIA_BACKEND", raising=False)
    import quantis.config.media_backend as mb

    monkeypatch.setattr(mb, "_BUILD_BACKEND", "vlc")
    assert resolve_media_backend() == "vlc"
