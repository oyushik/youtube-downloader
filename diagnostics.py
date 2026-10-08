"""Explicit, opt-in smoke test for the packaged app; writes a JSON report."""
from __future__ import annotations

import importlib.resources
import json
from pathlib import Path
import threading
import traceback

import yt_dlp
from yt_dlp.extractor.youtube.pot._registry import _pot_providers

from app_runtime import BundledRuntime, run_tool
from download_engine import DownloadEngine


def run(report_path: Path, test_url: str | None = None, playlist_url: str | None = None) -> int:
    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "checks": {}, "events": []}
    cancel = threading.Event()

    def emit(kind: str, data: dict) -> None:
        if kind != "progress":
            report["events"].append({"kind": kind, **data})

    try:
        from desktop import DownloadApp
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        app = DownloadApp(root)
        for step in range(4):
            app.show_step(step)
            root.update_idletasks()
        root.destroy()
        report["checks"]["gui"] = "all four pages constructed"
        with BundledRuntime(cancel) as runtime:
            process = runtime.process
            report["checks"]["provider"] = runtime.base_url
            report["checks"]["node"] = run_tool([str(runtime.node), "--version"], cancel).strip()
            report["checks"]["ffmpeg"] = run_tool([str(runtime.ffmpeg_dir / "ffmpeg.exe"), "-version"], cancel).splitlines()[0]
            engine = DownloadEngine(runtime, cancel, emit)
            with yt_dlp.YoutubeDL(engine.options()):
                providers = [cls.PROVIDER_NAME for cls in _pot_providers.value.values()]
            assert "bgutil:http" in providers, providers
            report["checks"]["plugins"] = providers
            solver = importlib.resources.files("yt_dlp_ejs.yt.solver")
            assert solver.joinpath("core.min.js").is_file()
            assert solver.joinpath("lib.min.js").is_file()
            report["checks"]["ejs"] = "bundled solver files found"
            media = report_path.parent / "smoke-media"
            media.mkdir(exist_ok=True)
            fixture = media / "fixture.mkv"
            run_tool([str(runtime.ffmpeg_dir / "ffmpeg.exe"), "-y", "-v", "error", "-f", "lavfi",
                      "-i", "color=c=blue:s=160x90:r=5:d=1", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                      "-c:v", "libx264", "-c:a", "aac", "-shortest", str(fixture)], cancel)
            assert engine.probe(fixture) == {"audio", "video"}
            report["checks"]["media"] = "FFmpeg generated an MKV; FFprobe verified video and audio"
            if playlist_url:
                listing = engine.inspect(playlist_url, True)
                report["checks"]["playlist"] = {"title": listing.title, "count": len(listing.videos)}
            if test_url:
                listing = engine.inspect(test_url, False)
                result = engine.download(listing, media, False, True)
                assert result["success"] == 1 and not result["failed"], result
                actual_files = [path for path in media.glob("*.mkv") if path != fixture]
                assert actual_files and engine.probe(actual_files[-1]) == {"audio", "video"}
                waves = list((media / "audio only").glob("*.wav"))
                if waves:
                    assert engine.probe(waves[-1]) == {"audio"}
                report["checks"]["download"] = result
        assert process.poll() is not None
        report["checks"]["provider_shutdown"] = "child exited"
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
