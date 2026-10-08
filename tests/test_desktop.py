from pathlib import Path
import gc
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from desktop import DownloadApp
from download_engine import Video, VideoList
from download_history import DownloadHistory


class DesktopTests(unittest.TestCase):
    def tearDown(self):
        # Tk variables must be collected on the UI thread before the next worker starts.
        gc.collect()

    def test_wizard_passes_reviewed_list_and_settings_to_worker(self):
        root = tk.Tk()
        root.withdraw()
        app = None
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
                app = DownloadApp(root, Path(temporary) / "history.sqlite3")
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
                records = DownloadHistory(app.history.path).list_downloads()
                self.assertEqual(len(records), 1)
                self.assertEqual(records[0]["state"], "완료")
                self.assertEqual(records[0]["success"], 1)
                app.history_button.invoke()
                self.assertEqual(len(app.history_window.jobs.get_children()), 1)
                self.assertEqual(app.history_window.items.set("0", "title"), "테스트 영상")
                self.assertEqual(app.step, 3)
                window = app.history_window
                app.open_history()
                self.assertIs(app.history_window, window)
                window.destroy()
                app.open_history()
                self.assertEqual(app.history_window.items.set("0", "state"), "완료")
                app.next()
                self.assertEqual(app.step, 0)
        finally:
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.destroy()

    def test_history_failure_does_not_prevent_download(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                app = DownloadApp(root, Path(temporary) / "history.sqlite3")
                listing = VideoList("영상", [Video(1, "test", "영상", "https://youtu.be/test")], False)
                app.listing = listing
                app.show_step(2)
                app.folder.set(temporary)
                with patch.object(app.history, "start", side_effect=OSError("read only")), \
                     patch("desktop.BundledRuntime"), patch("desktop.DownloadEngine") as engine, \
                     patch("desktop.messagebox.showwarning") as warning:
                    engine.return_value.download.return_value = {"success": 1, "failed": [], "total": 1}
                    app.next()
                    deadline = time.monotonic() + 5
                    while app.busy and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertFalse(app.busy)
                    self.assertIn("성공 1개", app.status.get())
                    warning.assert_called_once()
                    engine.return_value.download.assert_called_once()
        finally:
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.destroy()


if __name__ == "__main__":
    unittest.main()
