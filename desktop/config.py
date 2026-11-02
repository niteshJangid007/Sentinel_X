"""Paths, ports and runtime environment for the desktop shell.

Read-only with respect to the website checkout: this module loads the project's
own ``scripts/local_config.py`` to build the same DATABASE_URL the website
launcher uses, but never writes inside the checkout.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
from pathlib import Path

APP_NAME = "SentinelX Desktop"
APP_TITLE = "Sentinelx \u00b7 Security control center"
DEFAULT_PORT = 8000
PORT_ATTEMPTS = 20

DESKTOP_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT_DIR = DESKTOP_DIR.parent / "SentinelX"


class DesktopError(RuntimeError):
    """A startup problem that should be shown to the user verbatim."""


def portable() -> bool:
    """True when running from a self-contained bundle (SQLite, no Docker)."""
    if os.getenv("SENTINELX_PORTABLE", "").strip() in ("1", "true", "yes"):
        return True
    return (DESKTOP_DIR / "portable.mode").is_file()


def project_dir() -> Path:
    """The website checkout, overridable with SENTINELX_PROJECT_DIR."""
    configured = os.getenv("SENTINELX_PROJECT_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    candidates = (
        DEFAULT_PROJECT_DIR,
        DESKTOP_DIR / "website",
        DESKTOP_DIR.parent / "website",
    )
    for candidate in candidates:
        if (candidate / "app" / "main.py").is_file():
            return candidate.resolve()
    return DEFAULT_PROJECT_DIR.resolve()


def require_project_dir() -> Path:
    root = project_dir()
    required = (
        root / "app" / "main.py",
        root / "app" / "static" / "index.html",
        root / "app" / "static" / "app.js",
    )
    missing = [str(part.relative_to(root)) for part in required if not part.is_file()]
    if missing:
        raise DesktopError(
            f"The SentinelX website files were not found in:\n{root}\n\n"
            f"Missing: {', '.join(missing)}\n\n"
            "Keep the 'SentinelX' folder next to 'SentinelX Desktop', or set "
            "SENTINELX_PROJECT_DIR to its location."
        )
    return root


_DATA_DIR: Path | None = None


def data_dir() -> Path:
    """Writable per-user area: logs, window storage and the instance lock.

    Falls back to a folder inside the app when the usual per-user location is
    read-only, so a locked-down machine still starts.
    """
    global _DATA_DIR
    if _DATA_DIR is not None:
        return _DATA_DIR

    candidates: list[Path] = []
    override = os.getenv("SENTINELX_DESKTOP_DATA", "").strip()
    if override:
        candidates.append(Path(override).expanduser())
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
    if base:
        candidates.append(Path(base) / "SentinelX Desktop")
    candidates.append(DESKTOP_DIR / "runtime" / "userdata")

    problems: list[str] = []
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write-check"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as error:
            problems.append(f"{path}: {error}")
            continue
        _DATA_DIR = path
        return path
    raise DesktopError(
        "SentinelX Desktop cannot write its settings or logs.\n\n"
        "Set SENTINELX_DESKTOP_DATA to a writable folder and try again.\n\n"
        + "\n".join(problems)
    )


def logs_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def window_storage_dir() -> Path:
    """WebView2 profile so the Gold/Street edition choice survives restarts."""
    path = data_dir() / "window"
    path.mkdir(parents=True, exist_ok=True)
    return path


def edge_profile_dir() -> Path:
    path = data_dir() / "browser-profile"
    path.mkdir(parents=True, exist_ok=True)
    return path


def icon_path() -> Path:
    return DESKTOP_DIR / "assets" / "icon.ico"


def runtime_file() -> Path:
    return data_dir() / "runtime.json"


def lock_file() -> Path:
    return data_dir() / "instance.lock"


def base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def health_url(port: int) -> str:
    return base_url(port) + "/health"


def port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def choose_port(preferred: int = DEFAULT_PORT) -> int:
    for candidate in range(preferred, preferred + PORT_ATTEMPTS):
        if port_is_free(candidate):
            return candidate
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _load_local_config(root: Path):
    """Import the project's own configuration parser, if it is present."""
    script = root / "scripts" / "local_config.py"
    if not script.is_file():
        return None
    spec = importlib.util.spec_from_file_location("sentinelx_local_config", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def database_url(root: Path) -> str:
    """The same DATABASE_URL resolution the website launcher performs.

    In portable mode there is no PostgreSQL: the API falls back to the local
    SQLite file the project already supports, so the shared app needs nothing
    installed.
    """
    if portable():
        return ""

    explicit = os.getenv("DATABASE_URL", "").strip()
    if explicit:
        return explicit

    local_config = _load_local_config(root)
    if local_config is not None:
        try:
            return local_config.database_url(create=False)  # type: ignore[attr-defined]
        except (RuntimeError, ValueError) as error:
            raise DesktopError(str(error)) from error

    values = _parse_env_file(root / ".env")
    password = values.get("POSTGRES_PASSWORD", "")
    if not password:
        raise DesktopError(
            "PostgreSQL is not configured yet.\n\n"
            "Run Start-Sentinelx.cmd once so the website launcher creates .env, "
            "or set POSTGRES_PASSWORD in the project's .env file."
        )
    from urllib.parse import quote

    user = quote(values.get("POSTGRES_USER", "sentinelx"), safe="")
    name = quote(values.get("POSTGRES_DB", "sentinelx"), safe="")
    port = int(values.get("SENTINELX_POSTGRES_PORT", "55432"))
    return f"postgresql://{user}:{quote(password, safe='')}@127.0.0.1:{port}/{name}"


def postgres_host_port(root: Path, destination: str) -> tuple[str, int] | None:
    """Host and port of the configured PostgreSQL server, for readiness checks."""
    from urllib.parse import urlsplit

    try:
        parsed = urlsplit(destination)
    except ValueError:
        return None
    if not parsed.hostname:
        return None
    return parsed.hostname, parsed.port or 5432


def backend_environment(root: Path, destination: str) -> dict[str, str]:
    """Exact environment for the API process; nothing is written to the checkout."""
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    # Keep the website checkout byte-for-byte unchanged: no new __pycache__ files.
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.setdefault("PYTHONIOENCODING", "utf-8")
    environment.pop("SECUREFLOW_DB", None)
    if destination:
        environment["DATABASE_URL"] = destination
    else:
        # Portable mode: local SQLite file, no PostgreSQL, no Docker.
        environment.pop("DATABASE_URL", None)
        environment.pop("SENTINELX_ENV", None)
        environment.pop("SECUREFLOW_ENV", None)
        environment["SECUREFLOW_DB"] = str(data_dir() / "sentinelx.db")
    return environment


def lan_address(port: int) -> str:
    """Best-effort LAN URL a phone on the same Wi-Fi can open."""
    import socket

    candidates: list[str] = []
    for target in (("8.8.8.8", 80), ("192.168.1.1", 80)):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(target)
                candidates.append(probe.getsockname()[0])
        except OSError:
            continue
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except OSError:
        pass
    for address in candidates:
        if address and not address.startswith("127.") and address != "0.0.0.0":
            return f"http://{address}:{port}"
    return ""



def read_runtime() -> dict:
    try:
        return json.loads(runtime_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_runtime(port: int) -> None:
    payload = {"port": port, "pid": os.getpid(), "python": sys.executable}
    runtime_file().write_text(json.dumps(payload), encoding="utf-8")
