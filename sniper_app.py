#!/usr/bin/env python3
"""Entry point for the packaged desktop app (PyInstaller target)."""
import argparse
import sys

from desktop_app.server import main

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Vatican Sniper desktop app")
    p.add_argument("--no-browser", action="store_true",
                   help="don't auto-open the dashboard in a browser")
    p.add_argument("--port", type=int, default=None, help="dashboard port (default 8765)")
    p.add_argument("--self-test", action="store_true",
                   help="verify Playwright driver + CDP, then exit")
    args = p.parse_args()

    if args.self_test:
        from desktop_app.self_test import run_self_test
        sys.exit(0 if run_self_test() else 1)

    main(open_browser=not args.no_browser, port=args.port or 8765)
