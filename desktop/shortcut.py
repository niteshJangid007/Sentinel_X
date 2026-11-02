"""Create Desktop and Start Menu shortcuts once, so the app behaves like an installer."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from . import config

log = logging.getLogger("sentinelx.desktop")

POWERSHELL_SCRIPT = """\
$ErrorActionPreference = 'Continue'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$programs = [Environment]::GetFolderPath('Programs')
$targets = @(
    (Join-Path $desktop 'SentinelX Desktop.lnk'),
    (Join-Path $programs 'SentinelX Desktop.lnk')
)
$failed = @()
foreach ($target in $targets) {
    try {
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Force -ErrorAction Stop
        }
        $shortcut = $shell.CreateShortcut($target)
        $shortcut.TargetPath = '__PYTHONW__'
        $shortcut.Arguments = '"__SCRIPT__"'
        $shortcut.WorkingDirectory = '__WORKDIR__'
        $shortcut.IconLocation = '__ICON__'
        $shortcut.Description = 'Sentinelx security control center'
        $shortcut.WindowStyle = 1
        $shortcut.Save()
    } catch {
        $failed += ($target + ' -> ' + $_.Exception.Message)
    }
}
if ($failed.Count -gt 0) {
    [Console]::Error.WriteLine(($failed -join "`n"))
    exit 1
}
"""


def _marker() -> Path:
    return config.data_dir() / "shortcuts-created.txt"


def _quote(value: Path) -> str:
    return str(value).replace("'", "''")


def ensure_shortcuts() -> None:
    if os.name != "nt" or _marker().is_file():
        return
    try:
        override = os.environ.get("SENTINELX_PYTHONW", "").strip()
        pythonw = (
            Path(override)
            if override
            else config.DESKTOP_DIR / "runtime" / ".venv" / "Scripts" / "pythonw.exe"
        )
        script = config.DESKTOP_DIR / "SentinelX Desktop.pyw"
        icon = config.icon_path()
        if not pythonw.is_file() or not script.is_file():
            log.debug("Shortcut prerequisites missing; skipping")
            return

        powershell = (
            POWERSHELL_SCRIPT.replace("__PYTHONW__", _quote(pythonw))
            .replace("__SCRIPT__", _quote(script))
            .replace("__WORKDIR__", _quote(config.DESKTOP_DIR))
            .replace("__ICON__", _quote(icon))
        )
        script_path = config.data_dir() / "create-shortcuts.ps1"
        script_path.write_text(powershell, encoding="utf-8")

        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script_path),
            ],
            capture_output=True,
            timeout=60,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if completed.returncode == 0:
            _marker().write_text("created\n", encoding="utf-8")
            log.info("Desktop and Start Menu shortcuts created")
        else:
            log.warning(
                "Shortcut creation failed: %s",
                completed.stderr.decode("utf-8", "replace")[:400],
            )
    except Exception:
        # Shortcuts are a convenience; never let them block startup.
        log.exception("Could not create shortcuts")
