from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from app_runtime import Cancelled
from download_engine import DownloadEngine, Video, VideoList, build_base_name, sanitize_name, validate_url


class InputTests(unittest.TestCase):
    def test_youtube_links_and_mode(self):
        self.assertEqual(validate_url("youtu.be/abc123#t=1", False), "https://youtu.be/abc123")
        self.assertIn("list=PL123", validate_url("https://www.youtube.com/playlist?list=PL123", True))
        self.assertIn("/shorts/", validate_url("https://www.youtube.com/shorts/abc123", False))
        for value in ("https://youtube.com.evil.test/watch?v=abc", "file:///tmp/video", "https://youtube.com@evil.test/watch?v=a",
                      "https://youtube.com:4416/watch?v=a", "https://example.com/watch?v=a"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_url(value, False)
        with self.assertRaises(ValueError):
            validate_url("https://youtube.com/watch?v=abc", True)
        with self.assertRaises(ValueError):
            validate_url("https://youtube.com/playlist?list=PL123", False)

    def test_windows_names_and_duplicate_titles(self):
        self.assertEqual(sanitize_name("CON.txt"), "_CON.txt")
        self.assertEqual(sanitize_name(" 한글 : 제목?.  "), "한글 _ 제목_")
        used = {"same", "same [abc]"}
        name = build_base_name("Same", 2, 3, False, "abc", used)
        self.assertEqual(name, "Same [abc] (2)")
        self.assertIn(name.casefold(), used)
        self.assertEqual(build_base_name("제목", 7, 1000, True, "id", set()), "0007 - 제목")


class DownloadTests(unittest.TestCase):
    def make_engine(self):
        events = []
        engine = DownloadEngine(None, threading.Event(), lambda kind, data: events.append((kind, data)))
        return engine, events

    def test_transient_failure_retried_after_other_videos_and_existing_names_reserved(self):
        engine, events = self.make_engine()
        listing = VideoList("목록", [Video(1, "a", "Same", "a"), Video(3, "b", "Second", "b")], True)
        attempts = []
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "목록"
            target.mkdir()
            original = target / "Same.mkv"
            original.write_bytes(b"existing")

            def download(video, folder, total, numbered, separate, used):
                self.assertIn("same", used)
                attempts.append(video.video_id)
                if attempts == ["a"]:
                    raise RuntimeError("HTTP Error 403")
                return folder / "new.mkv"

            with patch.object(engine, "download_one", side_effect=download), patch("download_engine.random.uniform", return_value=0):
                result = engine.download(listing, Path(temporary), True, False)
            self.assertEqual(attempts, ["a", "b", "a"])
            self.assertEqual(result["success"], 2)
            self.assertEqual(result["failed"], [])
            self.assertEqual(original.read_bytes(), b"existing")
            self.assertIn(("overall", {"done": 2, "total": 2}), events)

    def test_private_failure_is_not_retried(self):
        engine, events = self.make_engine()
        listing = VideoList("video", [Video(1, "a", "Private", "a")], False)
        with tempfile.TemporaryDirectory() as temporary, patch.object(engine, "download_one", side_effect=RuntimeError("Private video")) as call:
            result = engine.download(listing, Path(temporary), False, False)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["success"], 0)
        self.assertEqual(len(result["failed"]), 1)

    def test_cancel_stops_before_next_video(self):
        engine, events = self.make_engine()
        listing = VideoList("videos", [Video(1, "a", "One", "a"), Video(2, "b", "Two", "b")], False)

        def download(*args):
            engine.cancel.set()
            return Path("finished.mkv")

        with tempfile.TemporaryDirectory() as temporary, patch.object(engine, "download_one", side_effect=download) as call:
            with self.assertRaises(Cancelled):
                engine.download(listing, Path(temporary), False, False)
        self.assertEqual(call.call_count, 1)
        self.assertTrue(any(kind == "item" and data["state"] == "완료" for kind, data in events))

    def test_single_video_named_from_resolved_title_without_overwrite(self):
        engine, _ = self.make_engine()
        engine.options = lambda: {}
        video = Video(1, "abc", "Flat title", "https://youtu.be/abc")

        class FakeYDL:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, *args, **kwargs):
                Path(self.options["outtmpl"].replace("%(ext)s", "mkv")).write_bytes(b"downloaded")
                return {"title": "한국어 제목", "id": "abc"}

        with tempfile.TemporaryDirectory() as temporary, patch("download_engine.yt_dlp.YoutubeDL", FakeYDL):
            folder = Path(temporary)
            original = folder / "한국어 제목.mkv"
            original.write_bytes(b"original")
            result = engine.download_one(video, folder, 1, False, False, {"한국어 제목"})
            self.assertEqual(result.name, "한국어 제목 [abc].mkv")
            self.assertEqual(result.read_bytes(), b"downloaded")
            self.assertEqual(original.read_bytes(), b"original")
            self.assertFalse(any(path.is_dir() for path in folder.iterdir()))


if __name__ == "__main__":
    unittest.main()
