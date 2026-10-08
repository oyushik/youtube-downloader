from pathlib import Path
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from desktop import DownloadApp
from download_engine import Video, VideoList


class DesktopTests(unittest.TestCase):
    def test_wizard_passes_reviewed_list_and_settings_to_worker(self):
        root = tk.Tk()
        root.withdraw()
        app = DownloadApp(root)
        listing = VideoList("테스트 재생목록", [Video(2, "test", "테스트 영상", "https://youtu.be/test", 19)], True)
        calls = []

        class Runtime:
            def __init__(self, cancel):
                pass
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass

        class Engine:
            def __init__(self, runtime, cancel, emit):
                self.emit = emit
            def inspect(self, url, playlist):
                calls.append(("inspect", playlist))
                return listing
            def download(self, **kwargs):
                calls.append(("download", kwargs))
                self.emit("item", {"row": 0, "state": "완료"})
                self.emit("overall", {"done": 1, "total": 1})
                return {"success": 1, "failed": [], "total": 1, "folder": str(kwargs["destination"])}

        def wait():
            deadline = time.monotonic() + 5
            while app.busy and time.monotonic() < deadline:
                root.update()
                time.sleep(0.01)
            self.assertFalse(app.busy, "background operation did not finish")

        try:
            with tempfile.TemporaryDirectory() as temporary, patch("desktop.BundledRuntime", Runtime), patch("desktop.DownloadEngine", Engine):
                app.mode.set("playlist")
                app.url.set("https://www.youtube.com/playlist?list=PL123")
                app.next()
                wait()
                self.assertEqual(app.step, 1)
                self.assertEqual(len(app.review_tree.get_children()), 1)
                app.next()
                self.assertEqual(app.step, 2)
                app.folder.set(temporary)
                app.numbered.set(True)
                app.separate.set(True)
                app.next()
                wait()
                self.assertEqual(app.step, 3)
                self.assertEqual(app.progress_tree.set("0", "state"), "완료")
                self.assertIs(calls[-1][1]["listing"], listing)
                self.assertEqual(calls[-1][1]["destination"], Path(temporary))
                self.assertTrue(calls[-1][1]["numbered"] and calls[-1][1]["separate"])
                app.next()
                self.assertEqual(app.step, 0)
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
