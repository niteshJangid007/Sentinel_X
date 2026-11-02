"""Optional free public HTTPS address for the running app.

Uses a Cloudflare quick tunnel (no account, no credits). When it is available a
phone can open the dashboard from any network — not only the same Wi-Fi — and
the browser can install it as an app. When it is not available the app simply
keeps the local network address.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config
from .config import DesktopError

URL_PATTERN = re.compile(r"https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def cloudflared_path() -> Path | None:
    candidates = (
        config.DESKTOP_DIR / "cloudflared.exe",
        config.DESKTOP_DIR / "tools" / "cloudflared.exe",
        config.DESKTOP_DIR / "python" / "cloudflared.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


class Tunnel:
    """Runs cloudflared and exposes the public URL once it is ready."""

    def __init__(self) -> None:
        self.process: subprocess.Popen | None = None
        self.url = ""

    def start(self, port: int, log_path: Path, timeout: float = 40.0) -> str:
        binary = cloudflared_path()
        if binary is None:
            return ""
        try:
            log = log_path.open("a", encoding="utf-8")
        except OSError:
            log = None
        try:
            self.process = subprocess.Popen(
                [str(binary), "tunnel", "--url", f"http://127.0.0.1:{port}",
                 "--no-autoupdate", "--metrics", "127.0.0.1:0"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as error:
            if log is not None:
                log.write(f"tunnel failed to start: {error}\n")
                log.close()
            return ""

        found = threading.Event()

        def read_output() -> None:
            assert self.process is not None and self.process.stdout is not None
            for line in self.process.stdout:
                if log is not None:
                    log.write(line)
                    log.flush()
                match = URL_PATTERN.search(line)
                if match and not found.is_set():
                    self.url = match.group(0)
                    found.set()

        reader = threading.Thread(target=read_output, name="sentinelx-tunnel", daemon=True)
        reader.start()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not found.wait(0.4):
            if self.process.poll() is not None:
                break
        if log is not None:
            log.close()
        if not self.url:
            self.stop()
        return self.url

    def stop(self) -> None:
        process = self.process
        self.process = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=8)
        except (subprocess.TimeoutExpired, OSError):
            try:
                process.kill()
            except OSError:
                pass
