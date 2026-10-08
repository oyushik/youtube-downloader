"""Persistent, per-user download history. Each write is a SQLite transaction."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

from download_engine import VideoList, sanitize_name


def default_history_path() -> Path:
    local_data = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    return local_data / "YouTubeDownloader" / "history.sqlite3"


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DownloadHistory:
    def __init__(self, path: Path | None = None):
        self.path = path if path is not None else default_history_path()

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=3)) as db:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    url TEXT NOT NULL,
                    folder TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT '미완료',
                    error TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS videos (
                    download_id INTEGER NOT NULL REFERENCES downloads(id),
                    position INTEGER NOT NULL,
                    playlist_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT '대기',
                    path TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (download_id, position)
                );
            """)
            with db:
                yield db

    def start(self, listing: VideoList, destination: Path) -> int:
        folder = destination / sanitize_name(listing.title, "playlist", 80) if listing.playlist else destination
        with self.connection() as db:
            row = db.execute(
                "INSERT INTO downloads (started_at, title, kind, url, folder) VALUES (?, ?, ?, ?, ?)",
                (timestamp(), listing.title, "재생목록" if listing.playlist else "개별 영상",
                 listing.source_url or (listing.videos[0].url if not listing.playlist else ""), str(folder)),
            )
            download_id = row.lastrowid
            db.executemany(
                "INSERT INTO videos (download_id, position, playlist_index, title, url) VALUES (?, ?, ?, ?, ?)",
                [(download_id, position, video.index, video.title, video.url)
                 for position, video in enumerate(listing.videos)],
            )
            return download_id

    def record_event(self, download_id: int, kind: str, data: dict) -> None:
        if kind not in {"folder", "item"}:
            return
        with self.connection() as db:
            if kind == "folder":
                db.execute("UPDATE downloads SET folder = ? WHERE id = ?", (data["path"], download_id))
            else:
                db.execute("UPDATE videos SET state = ?, path = ?, reason = ? WHERE download_id = ? AND position = ?",
                           (data["state"], data.get("path", ""), data.get("reason", ""), download_id, data["row"]))

    def finish(self, download_id: int, outcome: str, error: str = "") -> None:
        with self.connection() as db:
            if outcome == "complete":
                counts = db.execute("SELECT COUNT(*) AS total, SUM(state = '완료') AS success, SUM(state = '실패') AS failed FROM videos WHERE download_id = ?",
                                    (download_id,)).fetchone()
                if (counts["success"] or 0) + (counts["failed"] or 0) < counts["total"]:
                    state = "기록 불완전"
                else:
                    state = "완료" if counts["success"] == counts["total"] else "일부 실패" if counts["success"] else "실패"
            else:
                state = "중지됨" if outcome == "cancelled" else "실패"
            db.execute("""
                UPDATE videos SET state = CASE WHEN ? = 'complete' THEN '미확인'
                    WHEN state IN ('다운로드 중', '재시도 중') THEN ? ELSE '미실행' END
                WHERE download_id = ? AND state NOT IN ('완료', '실패')
            """, (outcome, "중지됨" if outcome == "cancelled" else "실패", download_id))
            db.execute("UPDATE downloads SET state = ?, finished_at = ?, error = ? WHERE id = ?",
                       (state, timestamp(), error, download_id))

    def list_downloads(self) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute("""
                SELECT d.*, COUNT(v.position) AS total,
                       COALESCE(SUM(v.state = '완료'), 0) AS success,
                       COALESCE(SUM(v.state = '실패'), 0) AS failed
                FROM downloads d LEFT JOIN videos v ON v.download_id = d.id
                GROUP BY d.id ORDER BY d.id DESC
            """)]

    def list_videos(self, download_id: int) -> list[dict]:
        with self.connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT * FROM videos WHERE download_id = ? ORDER BY position", (download_id,))]
