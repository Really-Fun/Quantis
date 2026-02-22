"""Модель трека

Треки могут быть двух типов:
1. Треки Яндекса
2. Треки YouTube

Классы:
1. Track - абстрактный класс трека
2. YandexTrack - класс трека Яндекса
3. YoutubeTrack - класс трека YouTube
"""

from dataclasses import dataclass

@dataclass
class Track:
    """Абстрактный класс трека"""
    track_id: int | str
    title: str
    author: str
    downloaded: bool = False
    source: str = ""
    listen_count: int = 0
    
    def __repr__(self):
        return f"{self.source}:{self.track_id}"
    
    def __str__(self):
        return f"{self.source} : {self.title} - {self.author}"
    
    def __eq__(self, value):
        if isinstance(value, self.__class__):
            return self.track_id == value.track_id
        if hasattr(value, "title") and hasattr(value, "author"):
            return (self.title, self.author) == (value.title, value.author)
        return False
    
    def __hash__(self):
        return hash(self.track_id)
    
    
@dataclass
class YandexTrack(Track):
    """Класс трека Яндекса"""
    source: str = "yandex"
    
@dataclass
class YoutubeTrack(Track):
    """Класс трека YouTube"""
    source: str = "youtube"