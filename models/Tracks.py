from dataclasses import dataclass

@dataclass
class Track:
    track_id: int | str
    title: str
    author: str
    source: str
    _track_path: str | None = None
    _cover_path: str | None = None
    
    def __repr__(self):
        return f"{self.source}:{self.track_id}"
    
    def __str__(self):
        return f"{self.source} : {self.title} - {self.author}"
    
    def __eq__(self, value):
        if isinstance(value, self.__class__):
            return self.track_id == value.track_id
        if (hasattr(value, "title") and hasattr(value, "author")):
            return (self.title, self.author) == (value.title, value.author)
        return False
    
    def __hash__(self):
        return hash(self.track_id)
    
    @property
    def track_path(self):
        return self._track_path
    
    @track_path.setter
    def track_path(self, value):
        self._track_path = value
    
    @property
    def cover_path(self):
        return self._cover_path
    
    @cover_path.setter
    def cover_path(self, value):
        self._cover_path = value
    
    
@dataclass
class YandexTrack(Track):
    source: str = "yandex"
    
@dataclass
class YoutubeTrack(Track):
    source: str = "youtube"