"""Windows desktop entry point. Run build.ps1 to create the portable EXE."""
from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="YouTube 다운로드")
    parser.add_argument("--self-test", type=Path, metavar="REPORT_JSON")
    parser.add_argument("--test-url")
    parser.add_argument("--playlist-url")
    args = parser.parse_args()
    if args.self_test:
        from diagnostics import run
        raise SystemExit(run(args.self_test, args.test_url, args.playlist_url))
    from desktop import main as open_window
    open_window()


if __name__ == "__main__":
    main()
