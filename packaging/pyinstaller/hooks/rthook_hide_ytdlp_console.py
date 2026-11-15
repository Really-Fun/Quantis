"""Keep subprocesses of the Windows GUI bundle from opening console windows."""

import sys

def _install_hidden_subprocesses():
    # Guard the base class, covering direct calls and yt-dlp's subclass.
    # Capture state locally: runtime hooks share PyInstaller's main namespace.
    import copy
    import functools
    import inspect
    import subprocess

    original_init = subprocess.Popen.__init__
    if getattr(original_init, "_quantis_hidden_console", False):
        return
    signature = inspect.signature(original_init)

    @functools.wraps(original_init)
    def hidden_init(self, *args, **kwargs):
        bound = signature.bind(self, *args, **kwargs)
        flags = bound.arguments.get("creationflags", 0)
        # CREATE_NEW_CONSOLE would override CREATE_NO_WINDOW.
        bound.arguments["creationflags"] = (
            flags & ~subprocess.CREATE_NEW_CONSOLE
        ) | subprocess.CREATE_NO_WINDOW
        startupinfo = bound.arguments.get("startupinfo")
        startupinfo = (
            copy.copy(startupinfo) if startupinfo is not None else subprocess.STARTUPINFO()
        )
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        bound.arguments["startupinfo"] = startupinfo
        original_init(*bound.args, **bound.kwargs)

    hidden_init._quantis_hidden_console = True
    subprocess.Popen.__init__ = hidden_init


if sys.platform == "win32":
    _install_hidden_subprocesses()
