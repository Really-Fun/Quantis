"""Инициализация клиентов:
- Яндекс Музыка
- YouTube Music
- Last.fm
- Spotify (TODO) - приоритет
- SoundCloud (TODO)
- Vk Music (TODO)

"""

from typing import List, Union

from yandex_music import ClientAsync
from yandex_music.exceptions import TimedOutError, NetworkError as NetworkErrorYandex
from pylast import WSError, NetworkError as NetworkErrorLastFm
from pylast import LastFMNetwork
from ytmusicapi import YTMusic
from keyring import get_password

from config.constants import (
    SERVICE_NAME_YANDEX,
    SERVICE_NAME_LASTFM_API,
    SERVICE_NAME_LASTFM_SECRET,
    USER,
)


class InitClients:
    """Класс, инициализирующий клиенты:
    init_yandex_client - Асинхронная версия яндекс музыки
    init_lastfm_client - синхронный клиент ютуб музыки
    init_ytmusic_client - синхронный клиент LastFm
    """

    def init_yandex_client(self) -> None:
        try:
            yandex_client = ClientAsync(get_password(SERVICE_NAME_YANDEX, USER))
        except TimedOutError:
            yandex_client = None
        except NetworkErrorYandex:
            yandex_client = None
        finally:
            return yandex_client

    def init_lastfm_client(self) -> None:
        LASTFM_API_KEY = get_password(SERVICE_NAME_LASTFM_API, USER)
        LASTFM_API_SECRET = get_password(SERVICE_NAME_LASTFM_SECRET, USER)
        if LASTFM_API_KEY is None or LASTFM_API_SECRET is None:
            lastfm_client = None
        try:
            lastfm_client = LastFMNetwork(LASTFM_API_KEY, LASTFM_API_SECRET)
        except WSError:
            pass
        except NetworkErrorLastFm:
            pass
        else:
            pass
        finally:
            return lastfm_client

    def init_ytmusic_client(self) -> None:
        ytmusic_client = YTMusic(language="ru", location="")
        return ytmusic_client


class GetClients:
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self) -> None:
        initializator = InitClients()
        self.__yandex = initializator.init_yandex_client()
        self.__youtube = initializator.init_ytmusic_client()
        self.__lastfm = initializator.init_lastfm_client()

    def get_yandex_client(self) -> ClientAsync | None:
        return self.__yandex

    def get_youtube_client(self) -> YTMusic:
        return self.__youtube

    def get_lastfm_client(self) -> LastFMNetwork:
        return self.__lastfm
