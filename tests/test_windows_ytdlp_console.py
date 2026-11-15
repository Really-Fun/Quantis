"""The Windows bundle must hide yt-dlp's console subprocesses."""

import runpy
import subprocess
import sys
from pathlib import Path

from yt_dlp.utils import Popen


def test_runtime_hook_hides_ytdlp_child_console(monkeypatch):
    seen = []
    original = Popen.__init__
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(Popen, "__init__", lambda self, args, *rest, **kw: seen.append(kw))
    hook = Path(__file__).resolve().parents[1] / "packaging/pyinstaller/hooks/rthook_hide_ytdlp_console.py"
    try:
        runpy.run_path(str(hook))
        Popen(["node.exe", "--version"])
        assert seen[0]["creationflags"] & 0x08000000
    finally:
        Popen.__init__ = original
