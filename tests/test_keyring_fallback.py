"""Без keyring-бэкенда (Linux без gnome-keyring/KWallet) токен просто пустой."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from keyring.errors import NoKeyringError

from quantis.config import credentials


def _no_keyring(*_args, **_kwargs):
    raise NoKeyringError("No recommended backend was available.")


@pytest.fixture
def no_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(credentials, "get_password", _no_keyring)


def test_yandex_token_without_keyring_is_empty(no_keyring: None) -> None:
    assert credentials.yandex_token() == ""


def test_yandex_streamer_token_without_keyring(no_keyring: None) -> None:
    from quantis.services.yandex_streamer import AsyncYandexStreamer

    assert AsyncYandexStreamer(MagicMock())._yandex_token() is None


def test_home_snapshot_without_keyring(no_keyring: None, qapp) -> None:
    from quantis.ui.viewmodels.home_vm import HomeViewModel

    vm = HomeViewModel(MagicMock(), MagicMock(), music=MagicMock())
    snapshot = vm._build_snapshot(
        recent_tracks=[],
        liked_tracks=[],
        downloaded=(),
        user_playlists=[],
        recommendation_tracks=(),
    )
    names = [playlist.name for playlist in snapshot.library_playlists]
    assert "Моя волна" not in names
    assert "Любимые" in names
