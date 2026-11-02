"""SentinelX Desktop entry point: startup choreography and shutdown."""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import backend as backend_module
from . import config, ui

log = logging.getLogger("sentinelx.desktop")


def setup_logging() -> Path:
    path = config.logs_dir() / "desktop.log"
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None and sys.stderr.isatty():
        root.addHandler(logging.StreamHandler(sys.stderr))
    return path


class InstanceLock:
    """One desktop instance per user; a second launch focuses the first."""

    def __init__(self) -> None:
        self._handle = None

    def acquire(self) -> bool:
        try:
            handle = config.lock_file().open("a+b")
        except OSError:
            return True  # Never block startup on a diagnostic-only lock.
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        try:
            handle.close()
        except OSError:
            pass


class Startup:
    """Owns the runtime pieces started by this process."""

    def __init__(self, preferred_port: int, lan: bool = False, share: bool = False):
        self.preferred_port = preferred_port
        self.lan = lan
        self.share = share
        self.public_url = ""
        self.tunnel = None
        self.backend: backend_module.Backend | None = None
        self.url = ""
        self.attached = False
        self.log_path: Path | None = None

    def run(self, status) -> None:
        root = config.require_project_dir()
        self.log_path = config.logs_dir() / "backend.log"

        existing = backend_module.running_instance_port()
        if existing:
            self.attached = True
            self.url = config.base_url(existing)
            log.info("Attached to the running SentinelX instance on port %s", existing)
            status("Connecting to the running SentinelX window\u2026")
            return

        status("Reading the database configuration…")
        destination = config.database_url(root)
        port = self.preferred_port or config.choose_port()
        if not config.port_is_free(port):
            port = config.choose_port()

        if destination:
            status("Starting PostgreSQL in Docker…")
            backend_module.ensure_postgres(root, destination, self.log_path)
        else:
            status("Starting the local database…")

        # The public link is created first: the server must know its public
        # origin, otherwise the browser's HTTPS origin fails its same-origin
        # check and the phone cannot sign in.
        public = ""
        if self.lan and self.share:
            status("Creating a public link for your phone…")
            try:
                from . import tunnel

                self.tunnel = tunnel.Tunnel()
                public = self.tunnel.start(port, config.logs_dir() / "tunnel.log")
                if public:
                    self.public_url = public
                    log.info("Public HTTPS address: %s", public)
                else:
                    log.warning("No public address was available; using the local network")
            except Exception:
                log.warning("The public tunnel could not be started", exc_info=True)

        environment = config.backend_environment(root, destination)
        if public:
            environment["SECUREFLOW_PUBLIC_ORIGIN"] = public
        host = "0.0.0.0" if self.lan else "127.0.0.1"
        self.backend = backend_module.Backend(
            root, port, environment, self.log_path, host=host
        )
        self.lan = self.lan and host == "0.0.0.0"

        status("Starting the SentinelX service…")
        self.backend.start()

        status("Loading your dashboard…")
        self.backend.wait_until_ready()
        # With a public link the window uses it too: session cookies and the
        # same-origin checks belong to that HTTPS origin.
        self.url = public or self.backend.url
        config.write_runtime(port)
        log.info("SentinelX service ready at %s", self.url)

        self._share_phone(port, status, public)

        # Import the window engine while the splash is still visible.
        try:
            import webview  # noqa: F401

            log.info("Native window engine available")
        except Exception:
            log.warning("Native window engine unavailable; Edge fallback will be used")

    def _share_phone(self, port: int, status, public: str = "") -> None:
        """Show the installable QR window for the phone."""
        if not self.lan:
            return
        shared = public or config.lan_address(port)
        if shared:
            log.info("Phone access: %s", shared)
            try:
                from . import share

                share.open(shared, installable=bool(self.public_url))
            except Exception:
                log.warning("Could not show the phone sharing window", exc_info=True)
        else:
            log.warning("LAN mode requested but no local network address was found")

    def shutdown(self) -> None:
        if self.tunnel is not None:
            log.info("Closing the public link")
            self.tunnel.stop()
            self.tunnel = None
        if self.backend is not None:
            log.info("Stopping the SentinelX service")
            self.backend.stop()
            self.backend = None
        if not self.attached:
            try:
                config.runtime_file().unlink(missing_ok=True)
            except OSError:
                pass


def _launch_window(startup: Startup, lock: InstanceLock) -> int:
    try:
        engine = ui.open_app_window(startup.url)
        log.info("Window closed (%s engine)", engine)
        return 0
    except config.DesktopError as error:
        log.error("Window error: %s", error)
        ui.message(config.APP_NAME, str(error), error=True)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        startup.shutdown()
        lock.release()


def run_gui(preferred_port: int, lan: bool = False, share: bool = False) -> int:
    # Installer-style convenience: one Desktop and Start Menu shortcut, once.
    from .shortcut import ensure_shortcuts

    threading.Thread(target=ensure_shortcuts, name="sentinelx-shortcuts", daemon=True).start()

    lock = InstanceLock()
    if not lock.acquire():
        existing = backend_module.running_instance_port()
        if existing:
            lock = InstanceLock()  # no lock held; window attaches and never stops it
            startup = Startup(preferred_port, lan, share)
            startup.attached = True
            startup.url = config.base_url(existing)
            startup._share_phone(existing, lambda text: None)
            return _launch_window(startup, lock)
        # A stale lock without a live service: continue as a fresh instance.
        lock = InstanceLock()

    splash = ui.Splash()
    startup = Startup(preferred_port, lan, share)
    outcome: dict[str, BaseException] = {}

    def work() -> None:
        try:
            startup.run(splash.set_status)
        except BaseException as error:  # surfaced in the GUI thread
            outcome["error"] = error
            log.exception("Startup failed")
        finally:
            splash.stop()

    splash.set_status("Checking your SentinelX installation\u2026")
    worker = threading.Thread(target=work, name="sentinelx-startup", daemon=True)
    worker.start()
    splash.run()
    worker.join(timeout=15)

    error = outcome.get("error")
    if error is not None:
        message = str(error) if isinstance(error, Exception) else repr(error)
        log_path = config.logs_dir() / "desktop.log"
        ui.message(
            config.APP_NAME,
            f"SentinelX Desktop could not start.\n\n{message}\n\nLog: {log_path}",
            error=True,
        )
        startup.shutdown()
        lock.release()
        return 1

    if not startup.url:
        ui.message(config.APP_NAME, "SentinelX Desktop could not start.", error=True)
        startup.shutdown()
        lock.release()
        return 1

    return _launch_window(startup, lock)


def _http_status(path: str, port: int) -> tuple[int, str]:
    request = urllib.request.Request(config.base_url(port) + path, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, ""


def run_self_test(preferred_port: int) -> int:
    """Headless verification of the desktop startup path (no window is shown)."""
    startup = Startup(preferred_port)
    checks: list[dict[str, object]] = []
    ok = True

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and condition
        checks.append({"check": name, "ok": bool(condition), "detail": detail})

    try:
        startup.run(lambda text: print(f"[startup] {text}", flush=True))
        port = int(startup.url.rsplit(":", 1)[1])
        status, home = _http_status("/", port)
        check("dashboard responds", status == 200, str(status))
        check(
            "dashboard is the SentinelX control center",
            "<title>Sentinelx \u00b7 Security control center</title>" in home,
            "",
        )
        check("dashboard keeps the themed views", 'id="root"' in home or "auth-pitch" in home)
        status, admin = _http_status("/admin", port)
        check("administrator portal responds", status == 200, str(status))
        check("administrator portal is unchanged", "Platform administration" in admin)
        status, css = _http_status("/assets/styles.css", port)
        check("stylesheets are served", status == 200 and len(css) > 1000, f"{len(css)} bytes")
        status, script = _http_status("/assets/app.js", port)
        check("dashboard script is served", status == 200 and len(script) > 1000, f"{len(script)} bytes")
        status, _ = _http_status("/api/v1/auth/me", port)
        check("API requires authentication", status == 401, str(status))
        try:
            import webview  # noqa: F401
            from importlib.metadata import version as _version

            check("native window engine is installed", True, f"pywebview {_version('pywebview')}")
        except Exception as error:
            check("native window engine is installed", False, str(error))
        if config.portable():
            database = config.data_dir() / "sentinelx.db"
            check("database is local SQLite", database.is_file(), str(database))
        else:
            check("database is PostgreSQL", startup.backend is not None,
                  "attached instance" if startup.attached else "new instance")
    except BaseException as error:
        log.exception("Self-test failed")
        checks.append({"check": "startup", "ok": False, "detail": str(error)})
        ok = False
    finally:
        startup.shutdown()

    print(json.dumps({"ok": ok, "checks": checks}, indent=2))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    # .NET Framework loads pythonnet's runtime assembly from this workspace; some
    # machines classify that path as remote and refuse to load it without this
    # documented compatibility switch. It must be set before the CLR starts.
    os.environ.setdefault("COMPLUS_LoadFromRemoteSources", "1")

    parser = argparse.ArgumentParser(prog=config.APP_NAME, add_help=True)
    parser.add_argument("--port", type=int, default=0, help="Preferred loopback port (default 8000)")
    parser.add_argument("--self-test", action="store_true", help="Verify startup without a window")
    parser.add_argument(
        "--lan",
        dest="lan",
        action="store_true",
        default=None,
        help="Also serve on the local network so phones on the same Wi-Fi can open it",
    )
    parser.add_argument(
        "--no-lan",
        dest="lan",
        action="store_false",
        help="Keep the server on this computer only",
    )
    parser.add_argument(
        "--share",
        dest="share",
        action="store_true",
        default=None,
        help="Create a free public HTTPS link so the phone app works on any network",
    )
    parser.add_argument(
        "--no-share",
        dest="share",
        action="store_false",
        help="Do not create a public link",
    )
    arguments = parser.parse_args(argv)
    lan = arguments.lan if arguments.lan is not None else config.portable()
    share = arguments.share if arguments.share is not None else config.portable()

    setup_logging()
    log.info("Starting %s (python %s)", config.APP_NAME, sys.version.split()[0])

    if arguments.self_test:
        return run_self_test(arguments.port)

    try:
        return run_gui(arguments.port, lan, share)
    except KeyboardInterrupt:
        return 0
    except Exception as error:  # last-resort dialog instead of a silent exit
        log.exception("Unhandled desktop error")
        ui.message(
            config.APP_NAME,
            f"SentinelX Desktop stopped unexpectedly.\n\n{error}\n\n"
            f"Log: {config.logs_dir() / 'desktop.log'}",
            error=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
