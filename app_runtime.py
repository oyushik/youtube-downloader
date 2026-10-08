"""Own the portable tools and the app's private localhost PO Token server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request


class Cancelled(Exception):
    pass


def check_cancel(cancel: threading.Event) -> None:
    if cancel.is_set():
        raise Cancelled("사용자가 작업을 중지했습니다.")


def runtime_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "runtime"
    return Path(__file__).resolve().parent / ".vendor"


def run_tool(command: list[str], cancel: threading.Event) -> str:
    check_cancel(cancel)
    with subprocess.Popen(
        command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ) as process:
        try:
            while True:
                check_cancel(cancel)
                try:
                    stdout, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode:
                raise RuntimeError(stderr.strip() or f"{Path(command[0]).name} 실행 실패")
            return stdout
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


class BundledRuntime:
    def __init__(self, cancel: threading.Event, root: Path | None = None):
        self.root = root or runtime_dir()
        self.cancel = cancel
        self.node = self.root / "node/node.exe"
        self.ffmpeg_dir = self.root / "ffmpeg"
        self.process: subprocess.Popen | None = None
        self.log = None
        self.base_url = ""

    def __enter__(self) -> BundledRuntime:
        required = [self.node, self.ffmpeg_dir / "ffmpeg.exe", self.ffmpeg_dir / "ffprobe.exe",
                    self.root / "provider-entry.mjs", self.root / "provider/build/main.js",
                    self.root / "plugins/bgutil/yt_dlp_plugins/extractor/getpot_bgutil_http.py"]
        for path in required:
            if not path.is_file():
                raise RuntimeError(f"앱 구성 파일이 없습니다: {path.name}\n완전한 EXE로 다시 실행해 주세요.")
        check_cancel(self.cancel)
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        self.log = tempfile.TemporaryFile(mode="w+b")
        env = {key: value for key, value in os.environ.items() if key not in {"NODE_OPTIONS", "NODE_PATH"}}
        try:
            self.process = subprocess.Popen(
                [str(self.node), str(self.root / "provider-entry.mjs"), "--host", "127.0.0.1", "--port", str(port)],
                cwd=self.root, stdin=subprocess.PIPE, stdout=self.log, stderr=self.log, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                check_cancel(self.cancel)
                if self.process.poll() is not None:
                    break
                try:
                    with opener.open(self.base_url + "/ping", timeout=0.5) as response:
                        data = json.load(response)
                    if data.get("version") == "2.0.2" and self.process.poll() is None:
                        return self
                except (OSError, ValueError):
                    pass
                self.cancel.wait(0.15)
            self.log.seek(0)
            detail = self.log.read().decode("utf-8", errors="replace")[-3000:]
            raise RuntimeError(f"다운로드 준비에 실패했습니다.\n{detail or '내장 서버 응답 시간 초과'}")
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.process is not None:
            if self.process.stdin:
                self.process.stdin.close()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
            self.process = None
        if self.log:
            self.log.close()
            self.log = None

    def __exit__(self, *_args) -> None:
        self.close()
