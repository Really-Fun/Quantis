from dataclasses import dataclass

@dataclass
class Track:
    track_id: int | str
    title: str
    author: str
    source: str
    downloaded: bool
    
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
    source: str = "yandex"
    
@dataclass
class YoutubeTrack(Track):
    source: str = "youtube"