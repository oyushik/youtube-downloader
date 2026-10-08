# Included software

This application includes Python, Tcl/Tk, yt-dlp, yt-dlp-ejs, bgutil-ytdlp-pot-provider,
Node.js, FFmpeg/FFprobe, and their dependencies. Their license files are embedded
alongside the corresponding packages in the executable's runtime payload.

- Python: https://www.python.org/ — PSF License
- Tcl/Tk: https://www.tcl.tk/ — Tcl/Tk License
- yt-dlp: https://github.com/yt-dlp/yt-dlp — Unlicense; dependency licenses also apply
- yt-dlp-ejs: https://github.com/yt-dlp/ejs — Unlicense; MIT/ISC components
- bgutil-ytdlp-pot-provider 2.0.2: https://github.com/Brainicism/bgutil-ytdlp-pot-provider/tree/2.0.2 — GPL-3.0-only
- Node.js 24.18.0: https://nodejs.org/dist/v24.18.0/ — MIT and bundled dependency licenses
- FFmpeg 9.0.2 essentials: https://www.gyan.dev/ffmpeg/builds/ — GPL build
- FFmpeg source: https://ffmpeg.org/releases/
- FFmpeg build information: https://www.gyan.dev/ffmpeg/builds/#about-these-builds

The exact download URLs and SHA-256 values are embedded in runtime/manifest.json
and recorded in prepare_runtime.py. The provider package-lock.json and dependency
license files are included. Rebuild instructions and this application's source are
in the project folder.
