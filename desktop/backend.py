"""Start PostgreSQL (Docker) and the existing SentinelX API process."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import config
from .config import DesktopError

CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.5)
    return False


def probe_health(port: int, timeout: float = 1.5) -> bool:
    """True only for this application's own health payload."""
    try:
        with urllib.request.urlopen(config.health_url(port), timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return False
    return payload.get("status") == "ok" and payload.get("service") == "Sentinelx"


def running_instance_port() -> int | None:
    """Port of an already running desktop/website instance, if it answers."""
    recorded = config.read_runtime().get("port")
    candidates = [recorded] if isinstance(recorded, int) else []
    candidates.append(config.DEFAULT_PORT)
    for port in candidates:
        if port and probe_health(port):
            return port
    return None


def ensure_postgres(root: Path, destination: str, log_path: Path) -> bool:
    """Bring up the project's PostgreSQL service; returns True if Docker was used.

    Skips Docker when the database already accepts connections, and skips
    entirely when the user configured an external DATABASE_URL. In portable
    mode there is no destination at all: the API uses local SQLite instead.
    """
    if not destination:
        return False
    target = config.postgres_host_port(root, destination)
    if target is None:
        raise DesktopError(
            "The configured DATABASE_URL is not a PostgreSQL URL.\n\n"
            "SentinelX Desktop uses the same PostgreSQL database as the website."
        )
    host, port = target
    if _port_open(host, port):
        return False

    if not (root / "compose.yaml").is_file():
        raise DesktopError(
            f"PostgreSQL is not reachable on {host}:{port} and no compose.yaml was "
            f"found in:\n{root}"
        )

    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting PostgreSQL ===\n")
        try:
            completed = subprocess.run(
                [
                    "docker",
                    "compose",
                    "-f",
                    str(root / "compose.yaml"),
                    "up",
                    "-d",
                    "--wait",
                    "db",
                ],
                cwd=str(root),
                env=dict(os.environ),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=300,
                creationflags=CREATE_NO_WINDOW,
            )
        except FileNotFoundError as error:
            raise DesktopError(
                "Docker Desktop is required because the website uses PostgreSQL in Docker.\n\n"
                "Install and start Docker Desktop, or point DATABASE_URL at another "
                "PostgreSQL server, then open SentinelX Desktop again."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise DesktopError(
                "PostgreSQL did not start within five minutes.\n\n"
                "Open Docker Desktop, check that it is running, and try again."
            ) from error

    if completed.returncode != 0:
        raise DesktopError(
            "PostgreSQL could not be started through Docker Compose.\n\n"
            "Open Docker Desktop and wait until it is running, then try again.\n"
            f"Details were written to:\n{log_path}"
        )
    if not wait_for_port(host, port, timeout=90):
        raise DesktopError(
            f"PostgreSQL did not begin listening on {host}:{port}.\n\n"
            "Open Docker Desktop, check the 'sentinelx' container, and try again."
        )
    return True


class Backend:
    """The unmodified SentinelX API, run as a child process on loopback."""

    def __init__(
        self,
        root: Path,
        port: int,
        environment: dict[str, str],
        log_path: Path,
        host: str = "127.0.0.1",
    ):
        self.root = root
        self.port = port
        self.environment = environment
        self.log_path = log_path
        self.host = host
        self.process: subprocess.Popen | None = None
        self._log = None

    @property
    def url(self) -> str:
        return config.base_url(self.port)

    def start(self) -> None:
        self._log = self.log_path.open("a", encoding="utf-8")
        self._log.write(
            f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} starting API on port {self.port} ===\n"
        )
        self._log.flush()
        command = [
            sys.executable,
            str(config.DESKTOP_DIR / "serve_entry.py"),
            "--host",
            self.host,
            "--port",
            str(self.port),
        ]
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(self.root),
                env=self.environment,
                stdout=self._log,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as error:
            raise DesktopError(f"The SentinelX service could not be started.\n\n{error}") from error

    def wait_until_ready(self, timeout: float = 120.0, on_tick=None) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process is not None and self.process.poll() is not None:
                raise DesktopError(
                    "The SentinelX service stopped during startup.\n\n"
                    f"Exit code: {self.process.returncode}\n"
                    f"Details:\n{self.log_path}"
                )
            if probe_health(self.port):
                return
            if on_tick is not None:
                on_tick()
            time.sleep(0.4)
        raise DesktopError(
            "The SentinelX service did not answer in time.\n\n"
            f"Details were written to:\n{self.log_path}"
        )

    def stop(self, timeout: float = 10.0) -> None:
        process = self.process
        self.process = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
            except OSError:
                pass
        if self._log is not None:
            try:
                self._log.close()
            except OSError:
                pass
            self._log = None
