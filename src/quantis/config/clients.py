"""Инициализация клиентов внешних сервисов (ленивая)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from yandex_music import ClientAsync
    from ytmusicapi import YTMusic

from quantis.config.constants import (
    SERVICE_NAME_YANDEX,
    USER,
)


class Clients:
    """Singleton-фабрика клиентов.

    Yandex и YouTube поднимаются отдельно при первом обращении —
    не блокируют старт приложения.
    """

    _instance: Clients | None = None
    _initialized: bool = False

    def __new__(cls) -> Clients:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._yandex: ClientAsync | None = None
        self._yandex_ready = False
        self._youtube: YTMusic | None = None
        self._youtube_ready = False
        self._initialized = True

    def get_yandex_client(self) -> ClientAsync | None:
        if not self._yandex_ready:
            self._yandex = self._init_yandex()
            self._yandex_ready = True
        return self._yandex

    def get_youtube_client(self) -> YTMusic:
        if not self._youtube_ready:
            self._youtube = self._init_youtube()
            self._youtube_ready = True
        assert self._youtube is not None
        return self._youtube

    def reload_yandex_client(self) -> None:
        """Перечитать токен из keyring (после сохранения в настройках)."""
        self._yandex = self._init_yandex()
        self._yandex_ready = True

    def reload_youtube_client(self) -> None:
        """Перечитать cookie (после сохранения в настройках)."""
        self._youtube = self._init_youtube()
        self._youtube_ready = True

    @staticmethod
    def _init_yandex() -> Any:
        from keyring import get_password
        from yandex_music import ClientAsync
        from yandex_music.exceptions import NetworkError as NetworkErrorYandex
        from yandex_music.exceptions import TimedOutError

        try:
            return ClientAsync(get_password(SERVICE_NAME_YANDEX, USER))
        except (TimedOutError, NetworkErrorYandex):
            return None

    @staticmethod
    def _init_youtube() -> Any:
        from ytmusicapi import YTMusic
        from ytmusicapi.exceptions import YTMusicError

        from quantis.config.credentials import yotube_cookie

        cookie = yotube_cookie()
        if cookie:
            try:
                return YTMusic(auth=cookie, language="ru", location="")
            except (YTMusicError, ValueError, TypeError, OSError) as e:
                print(f"Ошибка инициализации YTMusic с auth: {e}")
            except Exception as e:
                print(f"Ошибка инициализации YTMusic с auth: {e}")
        try:
            return YTMusic(language="ru", location="")
        except YTMusicError as e:
            print(f"Ошибка инициализации YTMusic: {e}")
            return YTMusic(language="ru", location="")
