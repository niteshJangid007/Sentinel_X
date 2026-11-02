"""Splash screen, native window and error dialogs for the desktop shell."""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import subprocess
import sys
import tkinter as tk
from pathlib import Path

from . import config

BACKGROUND = "#06080D"
PANEL = "#0C1119"
GOLD = "#C9A227"
CREAM = "#F3EBDD"
MUTED = "#8C93A3"
TRACK = "#1B2230"

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0

log = logging.getLogger("sentinelx.desktop")


def message(title: str, text: str, error: bool = False) -> None:
    """Native message box so startup failures are readable without a console."""
    if os.name == "nt":
        flags = 0x00000010 if error else 0x00000040  # MB_ICONERROR / MB_ICONINFORMATION
        try:
            ctypes.windll.user32.MessageBoxW(None, text, title, flags)
            return
        except OSError:
            pass
    print(f"{title}: {text}", file=sys.stderr)


class Splash:
    """Small branded startup window; updates arrive through a thread-safe queue."""

    WIDTH = 560
    HEIGHT = 300

    def __init__(self) -> None:
        self._events: "queue.Queue[str | None]" = queue.Queue()
        self._closed = False
        self.root = tk.Tk()
        self.root.title(config.APP_NAME)
        self.root.configure(bg=BACKGROUND)
        try:
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - self.WIDTH) // 2)
        y = max(0, (screen_h - self.HEIGHT) // 2)
        self.root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        self.canvas = tk.Canvas(
            self.root,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=BACKGROUND,
            highlightthickness=1,
            highlightbackground="#202838",
        )
        self.canvas.pack(fill="both", expand=True)
        self._draw()
        self._offset = 0.0
        self._animate()
        self.root.after(60, self._drain)

    # -- drawing -----------------------------------------------------------
    def _draw(self) -> None:
        cx = 52
        cy = 62
        radius = 20
        points = []
        for index in range(6):
            import math

            angle = math.radians(60 * index - 90)
            points.extend((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
        self.canvas.create_polygon(points, outline=GOLD, width=2, fill=PANEL)
        self.canvas.create_text(
            cx, cy + 1, text="S", fill=CREAM, font=("Georgia", 16, "bold")
        )
        self.canvas.create_text(
            84,
            54,
            text="SENTINELX",
            anchor="w",
            fill=CREAM,
            font=("Georgia", 22, "bold"),
        )
        self.canvas.create_text(
            85,
            80,
            text="SECURITY CONTROL CENTER",
            anchor="w",
            fill=GOLD,
            font=("Segoe UI", 8, "bold"),
        )
        self.canvas.create_text(
            32,
            150,
            text="Preparing your workspace",
            anchor="w",
            fill=CREAM,
            font=("Segoe UI", 11),
        )
        self._status_id = self.canvas.create_text(
            32,
            214,
            text="Starting\u2026",
            anchor="w",
            fill=MUTED,
            font=("Segoe UI", 9),
            width=self.WIDTH - 64,
        )
        self.canvas.create_rectangle(
            32, 250, self.WIDTH - 32, 253, fill=TRACK, width=0
        )
        self._bar = self.canvas.create_rectangle(
            32, 250, 132, 253, fill=GOLD, width=0
        )

    def _animate(self) -> None:
        if self._closed:
            return
        track = self.WIDTH - 64
        span = 150
        self._offset = (self._offset + 4) % (track + span)
        start = 32 + self._offset - span
        end = start + span
        self.canvas.coords(
            self._bar, max(32, start), 250, min(32 + track, end), 253
        )
        self.canvas.after(16, self._animate)

    # -- public API --------------------------------------------------------
    def set_status(self, text: str) -> None:
        self._events.put(text)

    def run(self) -> None:
        self.root.mainloop()

    def stop(self) -> None:
        self._events.put(None)

    # -- internals ---------------------------------------------------------
    def _drain(self) -> None:
        if self._closed:
            return
        try:
            while True:
                text = self._events.get_nowait()
                if text is None:
                    self._close()
                    return
                self.canvas.itemconfigure(self._status_id, text=text)
        except queue.Empty:
            pass
        self.root.after(80, self._drain)

    def _close(self) -> None:
        self._closed = True
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def _apply_window_icon(window) -> None:
    """Best-effort native polish: start maximized on the dashboard."""
    try:
        native = getattr(window, "native", None)
        if native is not None:
            native.WindowState = 2  # FormWindowState.Maximized
    except Exception:
        log.debug("Native window decoration is unavailable", exc_info=True)


def _find_edge() -> Path | None:
    candidates = [
        Path(os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.getenv("ProgramFiles", r"C:\Program Files"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.getenv("LOCALAPPDATA", ""))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _run_edge_window(url: str) -> None:
    """Fallback window using the Edge app mode already present on Windows."""
    edge = _find_edge()
    if edge is None:
        raise config.DesktopError(
            "No window engine is available.\n\n"
            "Install the Microsoft Edge WebView2 Runtime (or Microsoft Edge), "
            "then open SentinelX Desktop again."
        )
    command = [
        str(edge),
        f"--app={url}",
        f"--user-data-dir={config.edge_profile_dir()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1440,900",
    ]
    log.info("Opening fallback window: %s", " ".join(command))
    process = subprocess.Popen(command, creationflags=CREATE_NO_WINDOW)
    process.wait()


def open_app_window(url: str) -> str:
    """Show the dashboard in a native window; returns the engine that was used."""
    try:
        import webview
    except Exception:
        log.warning("pywebview is unavailable; using the Edge app window", exc_info=True)
        _run_edge_window(url)
        return "edge"

    try:
        window = webview.create_window(
            config.APP_TITLE,
            url=url,
            width=1440,
            height=900,
            min_size=(1024, 700),
            background_color=BACKGROUND,
            text_select=True,
        )
        webview.start(
            _apply_window_icon,
            window,
            gui="edgechromium",
            debug=False,
            private_mode=False,
            storage_path=str(config.window_storage_dir()),
            icon=str(config.icon_path()) if config.icon_path().is_file() else None,
        )
        return "webview"
    except Exception:
        log.exception("The native window failed; using the Edge app window")
        _run_edge_window(url)
        return "edge"
