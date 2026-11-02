"""Double-click entry point for SentinelX Desktop (runs without a console)."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

BASE = Path(__file__).resolve().parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))


def _fatal(error: BaseException) -> None:
    details = "".join(traceback.format_exception_only(type(error), error)).strip()
    message = (
        "SentinelX Desktop could not start.\n\n"
        f"{details}\n\n"
        "Delete the 'runtime' folder and run 'Start SentinelX Desktop.cmd' "
        "to repair the installation."
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "SentinelX Desktop", 0x10)
    except Exception:
        print(message, file=sys.stderr)
    log_dir = Path.home() / "AppData" / "Local" / "SentinelX Desktop" / "logs"
    (log_dir).mkdir(parents=True, exist_ok=True)
    (log_dir / "desktop-crash.log").write_text(
        "".join(traceback.format_exception(type(error), error, error.__traceback__)),
        encoding="utf-8",
    )


if __name__ == "__main__":
    try:
        from desktop.main import main

        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as error:  # noqa: BLE001 - shown to the user, then logged
        _fatal(error)
        raise SystemExit(1)
