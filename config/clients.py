import os
from typing import List, Union

from yandex_music import ClientAsync
from yandex_music.exceptions import TimedOutError, NetworkError as NetworkErrorYandex
from pylast import WSError, NetworkError as NetworkErrorLastFm
from pylast import LastFMNetwork
from ytmusicapi import YTMusic
from keyring import get_password

SERVICE_NAME_YANDEX: str = "YANDEX_TOKEN_NEON_APP"
SERVICE_NAME_LASTFM_API: str = "LASTFM_API_NEON_APP"
SERVICE_NAME_LASTFM_SECRET: str = "LASTFM_SECRET_NEON_APP"
USER: str = "NEON_APP"


class InitClients:
    """Класс, инициализирующий клиенты:
    _yandex_client - Асинхронная версия яндекс музыки
    _ytmusic_client - синхронный клиент ютуб музыки
    _lastfm_client - синхронный клиент LastFm
    """

    def __init__(self) -> None:
        """Инициализация клиентов
        """
        self._init_yandex_client()
        self._init_ytmusic_client()
        self._init_lastfm_client()
        
    def _init_yandex_client(self) -> None:
        try:
            self._yandex_client = ClientAsync(get_password(SERVICE_NAME_YANDEX, USER))
        except TimedOutError:
            pass
        except NetworkErrorYandex:
            pass
        else:
            pass
    
    def _init_lastfm_client(self) -> None:
        LASTFM_API_KEY = get_password(SERVICE_NAME_LASTFM_API, USER)
        LASTFM_API_SECRET = get_password(SERVICE_NAME_LASTFM_SECRET, USER)
        if LASTFM_API_KEY is None or LASTFM_API_SECRET is None:
            raise Exception("LastFm API key or secret is not set")
        try:
            self._lastfm_client = LastFMNetwork(LASTFM_API_KEY, LASTFM_API_SECRET)
        except WSError:
            pass
        except NetworkErrorLastFm:
            pass
        else:
            pass
    
    def _init_ytmusic_client(self) -> None:
        self._ytmusic_client = YTMusic()
        
    def return_clients(self) -> List[Union[ClientAsync, YTMusic, LastFMNetwork]]:
        return [self._yandex_client, self._ytmusic_client, self._lastfm_client]
        

class GetClients:
    
    def __new__(cls):
        if not hasattr(cls, "instance"):
            cls.instance = super().__new__(cls)
        return cls.instance
    
    def __init__(self) -> None:
        self.__yandex : ClientAsync
        self.__youtube: YTMusic
        self.__lastfm: LastFMNetwork
        for name, client in zip(["__yandex", "__youtube", "__lastfm"], InitClients().return_clients()):
            setattr(self, "_GetClients" + name, client)
    
    def get_yandex_client(self) -> ClientAsync:
        return self.__yandex
    
    def get_youtube_client(self) -> YTMusic:
        return self.__youtube
    
    def get_lastfm_client(self) -> LastFMNetwork:
        return self.__lastfm