"""Run standalone with Python, or as part of the regular pytest suite."""

import inspect
import runpy
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HOOK = (
    Path(__file__).resolve().parents[1]
    / "packaging/pyinstaller/hooks/rthook_hide_ytdlp_console.py"
)


@unittest.skipUnless(sys.platform == "win32", "Windows process startup flags")
class HiddenConsoleTests(unittest.TestCase):
    def setUp(self):
        self.seen = []
        signature = inspect.signature(subprocess.Popen.__init__)

        def record(*args, **kwargs):
            self.seen.append(signature.bind(*args, **kwargs).arguments)

        record.__signature__ = signature
        self.patcher = patch.object(subprocess.Popen, "__init__", record)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

        class RuntimeProcess(subprocess.Popen):
            pass

        self.runtime_process = RuntimeProcess
        runpy.run_path(str(HOOK))

    def launch(self, **kwargs):
        subprocess.Popen.__init__(object(), ["node.exe", "--version"], **kwargs)
        return self.seen[-1]

    def test_direct_subprocess_is_hidden(self):
        seen = self.launch()
        self.assertTrue(seen["creationflags"] & subprocess.CREATE_NO_WINDOW)
        self.assertTrue(seen["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)
        self.assertEqual(seen["startupinfo"].wShowWindow, subprocess.SW_HIDE)

    def test_preexisting_subclass_is_hidden(self):
        # The dependency can import its Popen subclass before the hook runs.
        self.runtime_process.__init__(object(), ["node.exe", "--version"])
        self.assertTrue(self.seen[-1]["creationflags"] & subprocess.CREATE_NO_WINDOW)

    def test_other_flags_are_preserved_and_new_console_is_removed(self):
        seen = self.launch(
            creationflags=(
                subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        )
        self.assertFalse(seen["creationflags"] & subprocess.CREATE_NEW_CONSOLE)
        self.assertTrue(seen["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP)
        self.assertTrue(seen["creationflags"] & subprocess.CREATE_NO_WINDOW)

    def test_caller_startupinfo_is_not_modified(self):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.wShowWindow = 5
        seen = self.launch(startupinfo=startupinfo)
        self.assertIsNot(seen["startupinfo"], startupinfo)
        self.assertEqual(startupinfo.wShowWindow, 5)
        self.assertEqual(startupinfo.dwFlags, 0)

    def test_positional_creationflags(self):
        signature = inspect.signature(subprocess.Popen.__init__)
        bound = signature.bind(object(), ["node.exe"])
        bound.apply_defaults()
        bound.arguments["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen.__init__(*bound.args, **bound.kwargs)
        self.assertTrue(self.seen[-1]["creationflags"] & subprocess.CREATE_NO_WINDOW)

    def test_repeated_hook_does_not_wrap_again(self):
        installed = subprocess.Popen.__init__
        runpy.run_path(str(HOOK))
        self.assertIs(subprocess.Popen.__init__, installed)
        self.launch()
        self.assertEqual(len(self.seen), 1)


@unittest.skipUnless(sys.platform == "win32", "Windows console integration")
class HiddenConsoleIntegrationTests(unittest.TestCase):
    def test_real_child_has_no_console_and_pipes_work(self):
        original = subprocess.Popen.__init__
        self.addCleanup(setattr, subprocess.Popen, "__init__", original)
        runpy.run_path(str(HOOK))
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import ctypes, sys; "
                    "print(ctypes.windll.kernel32.GetConsoleWindow()); "
                    "print('diagnostic', file=sys.stderr)"
                ),
            ],
            capture_output=True,
            text=True,
            check=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        self.assertEqual(result.stdout.strip(), "0")
        self.assertEqual(result.stderr.strip(), "diagnostic")


if __name__ == "__main__":
    unittest.main()
