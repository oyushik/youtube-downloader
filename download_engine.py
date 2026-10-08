"""Download logic shared by the desktop UI and smoke tests; no UI calls here."""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
import tempfile
import threading
import time
from typing import Callable
from urllib.parse import parse_qs, urlsplit, urlunsplit

import yt_dlp
from yt_dlp.globals import plugin_dirs

from app_runtime import BundledRuntime, Cancelled, check_cancel, run_tool, runtime_dir

# Use only the provider shipped with this app, independent of user yt-dlp settings.
plugin_dirs.value = [str(runtime_dir() / "plugins")]

INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                          *(f"LPT{i}" for i in range(1, 10))}
Emit = Callable[[str, dict], None]


def sanitize_name(name: str, fallback: str = "untitled", max_length: int = 120) -> str:
    name = INVALID_FILENAME_CHARS.sub("_", name or "")
    name = re.sub(r"\s+", " ", name).strip().rstrip(". ") or fallback
    if name.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES:
        name = "_" + name
    return name[:max_length].rstrip(". ") or fallback


def build_base_name(title: str, index: int, total: int, add_index: bool,
                    video_id: str | None, used_names: set[str]) -> str:
    title = sanitize_name(title, video_id or f"video_{index}")
    base = f"{index:0{max(3, len(str(total)))}d} - {title}" if add_index else title
    candidate = base
    if candidate.casefold() in used_names:
        candidate = f"{base} [{sanitize_name(video_id or str(index), max_length=40)}]"
    unique = candidate
    count = 2
    while unique.casefold() in used_names:
        unique = f"{candidate} ({count})"
        count += 1
    used_names.add(unique.casefold())
    return unique


def validate_url(value: str, playlist: bool) -> str:
    value = value.strip()
    if not value:
        raise ValueError("YouTube 링크를 입력해 주세요.")
    if "://" not in value:
        value = "https://" + value
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme not in {"http", "https"} or parsed.username or parsed.password
            or parsed.port not in {None, 80, 443}
            or not (host in {"youtube.com", "youtu.be"} or host.endswith(".youtube.com"))):
        raise ValueError("youtube.com 또는 youtu.be의 영상/재생목록 링크를 입력해 주세요.")
    query = parse_qs(parsed.query)
    if playlist and not query.get("list"):
        raise ValueError("재생목록 링크에는 list= 항목이 있어야 합니다.")
    if not playlist and not (query.get("v") or (host == "youtu.be" and parsed.path.strip("/"))
                             or parsed.path.startswith(("/shorts/", "/live/", "/embed/"))):
        raise ValueError("개별 영상 링크를 입력하거나 재생목록 모드로 변경해 주세요.")
    return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, ""))


def should_retry(message: str) -> bool:
    lower = message.lower()
    permanent = ("private video", "video is private", "removed", "copyright", "members-only")
    transient = ("this video is not available", "try again later", "http error 403", "http error 429",
                 "timed out", "temporarily", "sign in to confirm", "unable to download", "no video formats found")
    return not any(term in lower for term in permanent) and any(term in lower for term in transient)


@dataclass(frozen=True)
class Video:
    index: int
    video_id: str
    title: str
    url: str
    duration: float | None = None


@dataclass(frozen=True)
class VideoList:
    title: str
    videos: list[Video]
    playlist: bool


class DownloadEngine:
    def __init__(self, runtime: BundledRuntime, cancel: threading.Event, emit: Emit):
        self.runtime = runtime
        self.cancel = cancel
        self.emit = emit
        self.last_progress = 0.0

    # yt-dlp logger methods. Keeping text out of stdout also supports windowed EXEs.
    def debug(self, message: str) -> None:
        check_cancel(self.cancel)
        if not message.startswith("[debug]"):
            self.emit("log", {"message": message})

    def info(self, message: str) -> None:
        self.debug(message)

    def warning(self, message: str) -> None:
        self.emit("log", {"message": "참고: " + message})

    def error(self, message: str) -> None:
        self.emit("log", {"message": message})

    def options(self) -> dict:
        return {
            "extractor_args": {
                "youtube": {"player_client": ["mweb"], "lang": ["ko"]},
                "youtubepot-bgutilhttp": {"base_url": [self.runtime.base_url]},
            },
            "js_runtimes": {"node": {"path": str(self.runtime.node)}},
            "ffmpeg_location": str(self.runtime.ffmpeg_dir),
            "remote_components": set(), "cachedir": False,
            "logger": self, "quiet": True, "noprogress": True, "nocolor": True,
            "socket_timeout": 15, "sleep_interval_requests": 1,
            "sleep_interval": 5, "max_sleep_interval": 10,
            "retries": 3, "fragment_retries": 3, "extractor_retries": 3,
            "retry_sleep_functions": {key: lambda attempt: min(2 ** attempt, 20)
                                      for key in ("http", "fragment", "extractor")},
        }

    def inspect(self, url: str, playlist: bool) -> VideoList:
        url = validate_url(url, playlist)
        check_cancel(self.cancel)
        options = {**self.options(), "skip_download": True, "noplaylist": not playlist,
                   "extract_flat": "in_playlist" if playlist else False,
                   "ignoreerrors": True if playlist else False}
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
        check_cancel(self.cancel)
        if not info:
            raise RuntimeError("영상 정보를 가져오지 못했습니다. 링크와 접근 가능 여부를 확인해 주세요.")
        entries = info.get("entries") if playlist else [info]
        videos = []
        for position, entry in enumerate(entries or [], 1):
            if not entry:
                continue
            video_id = entry.get("id") or ""
            video_url = entry.get("webpage_url") or entry.get("url") or ""
            if not video_url.startswith(("https://", "http://")):
                video_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else ""
            try:
                index = int(entry.get("playlist_index") or position)
            except (TypeError, ValueError):
                index = position
            videos.append(Video(index, video_id, entry.get("title") or video_id or f"영상 {index}",
                                video_url, entry.get("duration")))
        if not videos:
            raise RuntimeError("다운로드할 영상이 없습니다. 재생목록의 공개 여부를 확인해 주세요.")
        return VideoList(info.get("title") or "재생목록", videos, playlist)

    def progress(self, data: dict) -> None:
        check_cancel(self.cancel)
        now = time.monotonic()
        if data.get("status") == "downloading" and now - self.last_progress < 0.15:
            return
        self.last_progress = now
        total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
        downloaded = data.get("downloaded_bytes") or 0
        self.emit("progress", {"percent": min(100, downloaded / total * 100) if total else 0,
                               "bytes": downloaded, "total": total,
                               "speed": data.get("speed"), "eta": data.get("eta"),
                               "status": data.get("status")})

    def postprocess(self, data: dict) -> None:
        check_cancel(self.cancel)
        self.emit("status", {"message": "영상·음성을 정리하는 중…"})

    def probe(self, path: Path) -> set[str]:
        result = run_tool([str(self.runtime.ffmpeg_dir / "ffprobe.exe"), "-v", "error",
                           "-show_entries", "stream=codec_type", "-of", "json", str(path)], self.cancel)
        return {stream.get("codec_type") for stream in json.loads(result).get("streams", [])}

    def download_one(self, video: Video, folder: Path, total: int, numbered: bool,
                     separate: bool, used_names: set[str]) -> Path:
        check_cancel(self.cancel)
        with tempfile.TemporaryDirectory(prefix=".yt-download-", dir=folder) as temporary:
            work = Path(temporary)
            options = {**self.options(), "format": "bestvideo+bestaudio/best", "merge_output_format": "mkv",
                       "outtmpl": str(work / "source.%(ext)s"), "noplaylist": True, "keepvideo": separate,
                       "overwrites": True, "progress_hooks": [self.progress],
                       "postprocessor_hooks": [self.postprocess],
                       "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mkv"}]}
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(video.url, download=True)
            final_mkv = work / "source.mkv"
            if not info or not final_mkv.exists():
                raise RuntimeError("최종 MKV 파일을 찾지 못했습니다.")
            base = build_base_name(info.get("title") or video.title, video.index, total, numbered,
                                   video.video_id or info.get("id"), used_names)
            pending = []
            try:
                if separate:
                    for source in list(work.iterdir()):
                        if not source.is_file() or source == final_mkv or source.suffix in {".part", ".ytdl"}:
                            continue
                        try:
                            streams = self.probe(source)
                        except (RuntimeError, ValueError):
                            continue
                        if "video" in streams and "audio" not in streams:
                            pending.append((source, folder / "video only" / f"{base}{source.suffix.lower()}"))
                        elif "audio" in streams and "video" not in streams:
                            wav = work / "converted.wav"
                            self.emit("status", {"message": "음성을 WAV 파일로 변환하는 중…"})
                            run_tool([str(self.runtime.ffmpeg_dir / "ffmpeg.exe"), "-y", "-v", "error",
                                      "-i", str(source), "-vn", "-c:a", "pcm_s16le", str(wav)], self.cancel)
                            pending.append((wav, folder / "audio only" / f"{base}.wav"))
                    if len(pending) < 2:
                        self.warning("이 영상에서는 일부 분리 스트림을 제공하지 않아 MKV만 저장되거나 별도 파일이 일부 생략됩니다.")
                destination = folder / f"{base}.mkv"
                pending.append((final_mkv, destination))
                check_cancel(self.cancel)
                for source, target in pending:
                    target.parent.mkdir(exist_ok=True)
                    # On Windows rename refuses an existing target, including a concurrent app's file.
                    if target.exists():
                        raise FileExistsError(f"같은 이름의 파일이 생겼습니다: {target.name}")
                    source.rename(target)
                return destination
            except BaseException:
                # Keep the name reserved if a separate output was already committed.
                if not any(target.exists() for _, target in pending):
                    used_names.discard(base.casefold())
                raise

    def download(self, listing: VideoList, destination: Path, numbered: bool, separate: bool) -> dict:
        folder = destination / sanitize_name(listing.title, "playlist", 80) if listing.playlist else destination
        folder.mkdir(parents=True, exist_ok=True)
        # Include earlier runs and separate outputs when avoiding filename collisions.
        used = {path.stem.casefold() for directory in (folder, folder / "audio only", folder / "video only")
                if directory.is_dir() for path in directory.iterdir() if path.is_file()}
        success = 0
        failures = []
        retry = []
        total = len(listing.videos)
        self.emit("folder", {"path": str(folder)})

        def attempt(row: int, video: Video, deferred: bool) -> None:
            nonlocal success
            check_cancel(self.cancel)
            self.emit("item", {"row": row, "state": "재시도 중" if deferred else "다운로드 중"})
            self.emit("status", {"message": f"[{row + 1}/{total}] {video.title}"})
            self.emit("progress", {"percent": 0, "bytes": 0, "total": 0})
            try:
                if not video.url:
                    raise ValueError("영상 URL을 확인할 수 없습니다.")
                path = self.download_one(video, folder, total, numbered and listing.playlist, separate, used)
            except Cancelled:
                raise
            except Exception as error:
                check_cancel(self.cancel)
                reason = str(error) or type(error).__name__
                if not deferred and should_retry(reason):
                    retry.append((row, video))
                    self.emit("item", {"row": row, "state": "재시도 대기", "reason": reason})
                else:
                    failures.append({"title": video.title, "index": video.index, "reason": reason})
                    self.emit("item", {"row": row, "state": "실패", "reason": reason})
            else:
                success += 1
                self.emit("item", {"row": row, "state": "완료", "path": str(path)})
            self.emit("overall", {"done": success + len(failures), "total": total})

        for row, video in enumerate(listing.videos):
            attempt(row, video, False)
        for row, video in retry:
            delay = random.uniform(20, 30)
            self.emit("status", {"message": f"{delay:.0f}초 뒤 재시도: {video.title}"})
            if self.cancel.wait(delay):
                raise Cancelled()
            attempt(row, video, True)
        return {"success": success, "failed": failures, "total": total, "folder": str(folder)}
