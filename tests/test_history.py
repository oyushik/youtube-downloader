from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from download_engine import Video, VideoList
from download_history import DownloadHistory, default_history_path


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.history = DownloadHistory(self.folder / "history.sqlite3")
        self.listing = VideoList("목록 제목", [Video(i + 1, str(i), f"영상 {i + 1}", f"https://youtu.be/video{i}")
                                            for i in range(3)], True, "https://youtube.com/playlist?list=PL123")

    def test_success_and_failure_survive_reopening_and_keep_video_details(self):
        job = self.history.start(self.listing, self.folder)
        self.history.record_event(job, "item", {"row": 0, "state": "완료", "path": str(self.folder / "영상 1.mkv")})
        self.history.record_event(job, "item", {"row": 1, "state": "실패", "reason": "Private video"})
        self.history.record_event(job, "item", {"row": 2, "state": "완료", "path": str(self.folder / "영상 3.mkv")})
        self.history.finish(job, "complete")
        reopened = DownloadHistory(self.history.path)
        record = reopened.list_downloads()[0]
        self.assertEqual((record["state"], record["success"], record["failed"], record["total"]), ("일부 실패", 2, 1, 3))
        self.assertEqual(record["url"], self.listing.source_url)
        self.assertEqual(record["folder"], str(self.folder / "목록 제목"))
        self.assertIsNotNone(record["finished_at"])
        self.assertEqual(reopened.list_videos(job)[1]["reason"], "Private video")

    def test_cancel_preserves_completed_videos_and_marks_unfinished_ones(self):
        job = self.history.start(self.listing, self.folder)
        self.history.record_event(job, "item", {"row": 0, "state": "완료", "path": "finished.mkv"})
        self.history.record_event(job, "item", {"row": 1, "state": "다운로드 중"})
        self.history.finish(job, "cancelled")
        self.assertEqual([row["state"] for row in self.history.list_videos(job)], ["완료", "중지됨", "미실행"])
        self.assertEqual(self.history.list_downloads()[0]["state"], "중지됨")
        self.assertEqual(self.history.list_videos(job)[0]["path"], "finished.mkv")

    def test_retry_updates_one_video_and_clears_previous_error(self):
        listing = VideoList("영상", [self.listing.videos[0]], False)
        job = self.history.start(listing, self.folder)
        self.history.record_event(job, "item", {"row": 0, "state": "재시도 대기", "reason": "HTTP Error 403"})
        self.history.record_event(job, "item", {"row": 0, "state": "완료", "path": "retried.mkv"})
        self.history.finish(job, "complete")
        self.assertEqual(len(self.history.list_videos(job)), 1)
        self.assertEqual(self.history.list_videos(job)[0]["reason"], "")
        self.assertEqual(self.history.list_downloads()[0]["state"], "완료")

    def test_multiple_app_instances_keep_both_downloads_and_unfinished_records(self):
        first = self.history.start(self.listing, self.folder)
        other = DownloadHistory(self.history.path)
        second = other.start(VideoList("개별 영상", [self.listing.videos[0]], False), self.folder)
        self.history.record_event(first, "item", {"row": 0, "state": "완료", "path": "first.mkv"})
        other.finish(second, "error", "서버 실행 실패")
        records = DownloadHistory(self.history.path).list_downloads()
        self.assertEqual([row["id"] for row in records], [second, first])
        self.assertEqual(records[0]["error"], "서버 실행 실패")
        self.assertEqual((records[1]["state"], records[1]["success"]), ("미완료", 1))

    def test_corrupt_file_is_not_silently_replaced(self):
        self.history.path.write_bytes(b"not a database")
        with self.assertRaises(sqlite3.DatabaseError):
            self.history.list_downloads()
        self.assertEqual(self.history.path.read_bytes(), b"not a database")

    def test_missing_result_is_reported_as_incomplete_history(self):
        job = self.history.start(self.listing, self.folder)
        self.history.record_event(job, "item", {"row": 0, "state": "완료", "path": "finished.mkv"})
        self.history.finish(job, "complete")
        self.assertEqual(self.history.list_downloads()[0]["state"], "기록 불완전")
        self.assertEqual(self.history.list_videos(job)[1]["state"], "미확인")

    def test_default_path_is_per_user_not_relative_to_executable(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.folder)}):
            self.assertEqual(default_history_path(), self.folder / "YouTubeDownloader/history.sqlite3")


if __name__ == "__main__":
    unittest.main()
