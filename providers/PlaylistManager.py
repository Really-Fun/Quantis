# from models.Playlists import Playlist


class PlaylistManager:
    _instance = None


    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, playlist = None):
        self.current_playlist = playlist

    def set_playlist(self, playlist = None):
        self.current_playlist = playlist