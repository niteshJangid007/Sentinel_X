"""First-run setup for SentinelX Desktop.

Creates an isolated runtime environment beside the app and installs the exact
website dependencies plus the native window engine. The website checkout is
only ever read.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / ".venv"
MARKER = HERE / "runtime" / "deps-ready.txt"
PROJECT = HERE.parent / "SentinelX"
LOCK = PROJECT / "requirements.lock"
DESKTOP_REQUIREMENTS = HERE / "requirements-desktop.txt"


def venv_python() -> Path:
    if os.name == "nt":
        return RUNTIME / "Scripts" / "python.exe"
    return RUNTIME / "bin" / "python"


def venv_pythonw() -> Path:
    if os.name == "nt":
        return RUNTIME / "Scripts" / "pythonw.exe"
    return venv_python()


def site_packages() -> Path:
    if os.name == "nt":
        return RUNTIME / "Lib" / "site-packages"
    return next(RUNTIME.glob("lib/python*/site-packages"))


def run(command: list[str], **kwargs) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True, **kwargs)


def fail(message: str) -> "NoReturn":  # type: ignore[name-defined]
    print("\n" + message, file=sys.stderr, flush=True)
    raise SystemExit(1)


def check_project() -> None:
    if not LOCK.is_file() or not (PROJECT / "app" / "main.py").is_file():
        fail(
            "The SentinelX website folder was not found next to this app.\n"
            f"Expected it at: {PROJECT}\n\n"
            "Keep 'SentinelX' and 'SentinelX Desktop' side by side, then try again."
        )


def create_venv() -> None:
    if venv_python().is_file():
        return
    MARKER.unlink(missing_ok=True)
    print("Creating the desktop runtime...", flush=True)
    try:
        run([sys.executable, "-m", "venv", str(RUNTIME)])
    except subprocess.CalledProcessError:
        # Some Windows setups cannot bootstrap pip inside a new environment.
        shutil.rmtree(RUNTIME, ignore_errors=True)
        run([sys.executable, "-m", "venv", "--without-pip", str(RUNTIME)])
    ensure_pip()


def ensure_pip() -> None:
    probe = subprocess.run(
        [str(venv_python()), "-m", "pip", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode == 0:
        return
    print("Installing pip into the runtime...", flush=True)
    import sysconfig

    source = Path(sysconfig.get_paths()["purelib"])
    target = site_packages()
    target.mkdir(parents=True, exist_ok=True)
    copied = False
    for item in source.glob("pip*"):
        if item.name.startswith("pip") and (
            item.is_dir() or item.name.endswith(".dist-info")
        ):
            destination = target / item.name
            if destination.exists():
                continue
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                shutil.copy2(item, destination)
            copied = True
    if not copied:
        run([str(venv_python()), "-m", "ensurepip", "--upgrade"])


def install_dependencies() -> None:
    if MARKER.is_file() and venv_python().is_file():
        return
    print("Installing SentinelX dependencies (first run only)...", flush=True)
    run(
        [
            str(venv_python()),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "-r",
            str(LOCK),
        ]
    )
    if DESKTOP_REQUIREMENTS.is_file():
        run(
            [
                str(venv_python()),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "-r",
                str(DESKTOP_REQUIREMENTS),
            ]
        )
    MARKER.write_text(
        "SentinelX Desktop runtime dependencies installed.\n", encoding="utf-8"
    )


def prepare_temp() -> None:
    """Keep pip's scratch files inside the app folder, for locked-down machines."""
    temp = HERE / "runtime" / "tmp"
    temp.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(temp)
    os.environ["TEMP"] = str(temp)


def main() -> int:
    prepare_temp()
    check_project()
    create_venv()
    ensure_pip()
    install_dependencies()
    print("\nSentinelX Desktop is ready.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except subprocess.CalledProcessError as error:
        fail(
            "Setup could not finish.\n\n"
            f"Command failed: {' '.join(map(str, error.cmd))}\n"
            "Check your internet connection, then run this launcher again."
        )
