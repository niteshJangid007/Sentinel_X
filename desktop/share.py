"""Show a QR code so a phone can open — or install — the running app."""

from __future__ import annotations

import base64
import subprocess
import sys

from . import config


def open(url: str, installable: bool = False) -> None:
    """Show the sharing window in its own process so the app is never blocked."""
    import json

    flags = 0x08000000 if sys.platform == "win32" else 0
    code = (
        "import sys; sys.path.insert(0, {root}); "
        "from desktop.share import main; raise SystemExit(main({url}, {installable}))"
    ).format(
        root=json.dumps(str(config.DESKTOP_DIR)),
        url=json.dumps(url),
        installable="True" if installable else "False",
    )
    subprocess.Popen(
        [sys.executable, "-c", code],
        close_fds=True,
        creationflags=flags,
        cwd=str(config.DESKTOP_DIR),
    )


def main(url: str, installable: bool = False) -> int:
    import tkinter as tk

    background = "#06080D"
    panel = "#0C1119"
    gold = "#C9A227"
    cream = "#F3EBDD"
    muted = "#8C93A3"

    root = tk.Tk()
    root.title("SentinelX \u00b7 mobile app")
    root.configure(bg=background)
    root.resizable(False, False)

    width, height = 420, 640
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    root.geometry(
        f"{width}x{height}+{max(0, screen_w - width - 60)}+{max(0, (screen_h - height) // 2)}"
    )

    tk.Label(
        root, text="MOBILE APP", bg=background, fg=gold,
        font=("Segoe UI", 10, "bold"),
    ).pack(pady=(22, 6))

    tk.Label(
        root,
        text="Install SentinelX on your phone" if installable else "Scan to open SentinelX",
        bg=background, fg=cream, font=("Georgia", 19, "bold"),
    ).pack(pady=(0, 4))

    tk.Label(
        root,
        text="Any network \u2014 this link is public." if installable
        else "Same Wi-Fi network as this computer.",
        bg=background, fg=muted, font=("Segoe UI", 9),
    ).pack(pady=(0, 14))

    frame = tk.Frame(root, bg=panel, highlightthickness=1, highlightbackground="#202838")
    frame.pack(padx=26)

    try:
        import segno

        uri = segno.make(url, error="m").png_data_uri(scale=6, border=2)
        payload = base64.b64encode(base64.b64decode(uri.split(",", 1)[1]))
        photo = tk.PhotoImage(data=payload)
        image = tk.Label(frame, image=photo, bg="#FFFFFF", bd=0)
        image.image = photo
        image.pack(padx=12, pady=12)
    except Exception:
        tk.Label(
            frame, text="QR code unavailable", bg=panel, fg=muted,
            font=("Segoe UI", 10), width=30, height=10,
        ).pack()

    tk.Label(
        root, text=url, bg=background, fg=cream,
        font=("Consolas", 11), wraplength=370, justify="center",
    ).pack(pady=(16, 8))

    hint = (
        "1. Scan the code\n"
        "2. Open the link in Chrome or Safari\n"
        "3. Menu \u2192 \u201cAdd to Home screen\u201d / \u201cInstall app\u201d\n\n"
        "The icon then opens fullscreen like a native app."
        if installable
        else
        "Scan with your phone camera, then sign in with the same account.\n"
        "Choose Allow if Windows asks about firewall access."
    )
    tk.Label(
        root, text=hint, bg=background, fg=muted,
        font=("Segoe UI", 8), justify="center",
    ).pack(pady=(4, 14))

    tk.Button(
        root, text="Close", command=root.destroy,
        bg=gold, fg="#0B0F17", activebackground="#E0B93A",
        font=("Segoe UI", 10, "bold"), relief="flat", padx=22, pady=6, bd=0,
        cursor="hand2",
    ).pack(pady=(0, 16))

    root.after(180000, root.destroy)
    root.mainloop()
    return 0


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    installable = len(sys.argv) > 2 and sys.argv[2].lower() == "true"
    raise SystemExit(main(url, installable))
