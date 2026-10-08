"""Download and prepare the Windows runtimes used by the EXE (build time only)."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / ".build-cache"
VENDOR = ROOT / ".vendor"
NODE_VERSION = "24.18.0"
PROVIDER_VERSION = "2.0.2"
DOWNLOADS = {
    "node-v24.18.0-win-x64.zip": (
        "https://nodejs.org/dist/v24.18.0/node-v24.18.0-win-x64.zip",
        "0ae68406b42d7725661da979b1403ec9926da205c6770827f33aac9d8f26e821",
    ),
    "bgutil-2.0.2.zip": (
        "https://github.com/Brainicism/bgutil-ytdlp-pot-provider/archive/refs/tags/2.0.2.zip",
        "df68ee6210e4960757bceae298927fb2ebd4d5cd9d390f9ff3a8287b0d2d1054",
    ),
    "ffmpeg-9.0.2-essentials.zip": (
        "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip",
        "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba",
    ),
}


def fetch(name: str) -> Path:
    url, expected = DOWNLOADS[name]
    path = CACHE / name
    if not path.exists():
        print(f"Downloading {name}", flush=True)
        temporary = path.with_suffix(".download")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as out:
            shutil.copyfileobj(response, out)
        temporary.replace(path)
    with path.open("rb") as source:
        actual = hashlib.file_digest(source, "sha256").hexdigest()
    if actual != expected:
        raise RuntimeError(f"Checksum mismatch: {path}\nExpected {expected}\nActual   {actual}")
    return path


def extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for name in bundle.namelist():
            if not (destination / name).resolve().is_relative_to(destination.resolve()):
                raise RuntimeError(f"Invalid archive path: {name}")
        bundle.extractall(destination)
        return destination / bundle.namelist()[0].split("/")[0]


def main() -> None:
    CACHE.mkdir(exist_ok=True)
    VENDOR.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "provider-entry.mjs", VENDOR / "provider-entry.mjs")
    plugin_source = importlib.metadata.distribution("bgutil-ytdlp-pot-provider").locate_file("yt_dlp_plugins")
    shutil.copytree(plugin_source, VENDOR / "plugins/bgutil/yt_dlp_plugins", dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    node_source = extract(fetch("node-v24.18.0-win-x64.zip"), CACHE / "node")
    node_dir = VENDOR / "node"
    node_dir.mkdir(exist_ok=True)
    shutil.copy2(node_source / "node.exe", node_dir / "node.exe")
    shutil.copy2(node_source / "LICENSE", node_dir / "LICENSE")

    provider_source = extract(fetch("bgutil-2.0.2.zip"), CACHE / "bgutil-source")
    server = provider_source / "server"
    node = node_source / "node.exe"
    npm = [str(node), str(node_source / "node_modules/npm/bin/npm-cli.js")]
    env = {**os.environ, "PATH": str(node_source) + os.pathsep + os.environ.get("PATH", ""),
           "npm_config_cache": str(CACHE / "npm")}
    marker = VENDOR / "provider-version.txt"
    if not marker.exists() or marker.read_text().strip() != PROVIDER_VERSION:
        subprocess.run([*npm, "ci", "--no-audit", "--no-fund"], cwd=server, env=env, check=True)
        subprocess.run([str(node), "node_modules/typescript/bin/tsc"], cwd=server, env=env, check=True)
        subprocess.run([*npm, "prune", "--omit=dev", "--no-audit", "--no-fund"], cwd=server, env=env, check=True)
        provider = VENDOR / "provider"
        provider.mkdir(exist_ok=True)
        for folder in ("build", "node_modules"):
            shutil.copytree(server / folder, provider / folder, dirs_exist_ok=True)
        for name in ("package.json", "package-lock.json"):
            shutil.copy2(server / name, provider / name)
        shutil.copy2(provider_source / "LICENSE", provider / "LICENSE")
        marker.write_text(PROVIDER_VERSION, encoding="utf-8")

    ffmpeg_source = extract(fetch("ffmpeg-9.0.2-essentials.zip"), CACHE / "ffmpeg")
    ffmpeg = VENDOR / "ffmpeg"
    ffmpeg.mkdir(exist_ok=True)
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        shutil.copy2(ffmpeg_source / "bin" / name, ffmpeg / name)
    for name in ("LICENSE", "README.txt"):
        if (ffmpeg_source / name).exists():
            shutil.copy2(ffmpeg_source / name, ffmpeg / name)
    (VENDOR / "manifest.json").write_text(json.dumps({
        "node": NODE_VERSION, "bgutil": PROVIDER_VERSION,
        "ffmpeg": ffmpeg_source.name, "downloads": DOWNLOADS,
    }, indent=2), encoding="utf-8")
    print("Bundled runtimes are ready.", flush=True)


if __name__ == "__main__":
    main()
