"""Starts the dashboard server with the phone-app (PWA) layer attached.

Run with the desktop app's Python:  python serve_entry.py --host 0.0.0.0 --port 8000
It adds both the desktop package and the website package to the import path,
which the embedded Python runtime does not do automatically.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for entry in (HERE / "website", HERE):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import uvicorn  # noqa: E402
from desktop.serve import app  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    uvicorn.run(
        app,
        host=arguments.host,
        port=arguments.port,
        workers=1,
        # Trust forwarded headers only from the local tunnel, which terminates
        # HTTPS and connects from 127.0.0.1. LAN clients keep their real scheme,
        # so the application's same-origin checks stay meaningful.
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
