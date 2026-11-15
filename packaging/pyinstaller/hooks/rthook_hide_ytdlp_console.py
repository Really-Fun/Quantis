"""Hide console windows created by yt-dlp's bundled JS runtime on Windows."""

import subprocess
import sys

if sys.platform == "win32":
    from yt_dlp.utils import Popen

    _original_init = Popen.__init__

    def _hidden_init(self, args, *remaining, **kwargs):
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        _original_init(self, args, *remaining, **kwargs)

    Popen.__init__ = _hidden_init
