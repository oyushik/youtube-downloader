# Build with: .venv\Scripts\python.exe -m PyInstaller --noconfirm YouTubeDownloader.spec
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH)
datas = [(str(root / ".vendor"), "runtime"), (str(root / "THIRD_PARTY_NOTICES.md"), ".")]
binaries = []
hiddenimports = []
for package in ("yt_dlp", "yt_dlp_ejs"):
    package_data, package_binaries, package_imports = collect_all(package)
    datas += package_data
    binaries += package_binaries
    hiddenimports += package_imports
datas += copy_metadata("bgutil-ytdlp-pot-provider")

a = Analysis(
    [str(root / "youtube-download.py")], pathex=[str(root)],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=["pytest", "unittest", "IPython", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="YouTubeDownloader", debug=False, strip=False, upx=False,
    console=False, disable_windowed_traceback=False,
)
