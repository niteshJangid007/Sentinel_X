"""Deterministic auto-fix proposals for selected findings.

Nothing is changed until the operator confirms: ``preview`` returns a diff and
the user must explicitly call ``apply``. Only rule-based, reviewable edits are
offered; findings without a safe transformation are reported as manual.
"""

from __future__ import annotations

import difflib
import io
import os
import re
import tempfile
import zipfile
from pathlib import Path

MAX_SOURCE_BYTES = 20 * 1024 * 1024

NOTE = (
    "Proposed change only. Review the diff before applying; SentinelX writes a "
    "patched copy of the project, it never edits your repository."
)


def storage_dir() -> Path:
    """Where patched archives are kept; follows the database location."""
    database = os.getenv("SECUREFLOW_DB", "").strip()
    base = Path(database).parent if database else Path(tempfile.gettempdir()) / "sentinelx"
    target = base / "remediations"
    target.mkdir(parents=True, exist_ok=True)
    return target


def source_path(scan_id: str) -> Path:
    return storage_dir() / f"source-{scan_id}.zip"


def store_source(scan_id: str, data: bytes) -> None:
    try:
        source_path(scan_id).write_bytes(data)
    except OSError:
        # Storage is a convenience; a failed write must not break the scan.
        pass


def load_source(scan_id: str) -> bytes | None:
    path = source_path(scan_id)
    try:
        return path.read_bytes() if path.is_file() else None
    except OSError:
        return None


def files_from_archive(data: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in archive.infolist():
                if entry.is_dir() or entry.file_size > MAX_SOURCE_BYTES:
                    continue
                name = entry.filename.replace("\\", "/").lstrip("./")
                if name.startswith("/") or ".." in name.split("/"):
                    continue
                if entry.file_size > 1024 * 1024:
                    continue
                files[name] = archive.read(entry)
    except (zipfile.BadZipFile, OSError):
        return {}
    return files


# --------------------------------------------------------------------- fixers


def _fix_dockerfile_user(text: str, finding: dict) -> str | None:
    lines = text.splitlines(keepends=True)
    changed = False
    for index, line in enumerate(lines):
        if re.match(r"(?i)^\s*USER\s+(?:root|0)\s*$", line.rstrip("\n")):
            lines[index] = re.sub(r"(?i)(USER\s+)(?:root|0)", r"\g<1>10001", line)
            changed = True
    return "".join(lines) if changed else None


def _fix_privileged(text: str, finding: dict) -> str | None:
    updated = re.sub(r"(?im)^(\s*)privileged\s*:\s*true\b", r"\1privileged: false", text)
    return updated if updated != text else None


def _fix_inner_html(text: str, finding: dict) -> str | None:
    updated = text.replace(".innerHTML =", ".textContent =").replace(".innerHTML=", ".textContent=")
    return updated if updated != text else None


FIXERS = (
    ("Docker image runs as root", _fix_dockerfile_user),
    ("Privileged container configuration", _fix_privileged),
    ("Dynamic HTML write requires injection review", _fix_inner_html),
)


def _select(finding: dict):
    title = str(finding.get("title", ""))
    for name, fixer in FIXERS:
        if name.lower() in title.lower():
            return fixer
    return None


def propose(finding: dict, files: dict[str, bytes]) -> dict:
    """Return a reviewable proposal; never changes anything."""
    path = str(finding.get("path") or "")
    if not path:
        return {"available": False, "reason": "This finding has no file location."}
    fixer = _select(finding)
    if fixer is None:
        return {
            "available": False,
            "reason": "No automated fix is defined for this finding type. "
            "Use the remediation guidance above.",
        }
    data = files.get(path)
    if data is None:
        return {"available": False, "reason": "The scanned source for this file is no longer stored."}
    try:
        original = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"available": False, "reason": "This file is not UTF-8 text."}

    updated = fixer(original, finding)
    if updated is None or updated == original:
        return {"available": False, "reason": "The rule no longer matches this file."}

    diff = "\n".join(
        difflib.unified_diff(
            original.splitlines(),
            updated.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    return {
        "available": True,
        "path": path,
        "diff": diff,
        "note": NOTE,
        "before": original,
        "after": updated,
    }


def patched_archive(original: bytes, path: str, new_text: str) -> bytes:
    """Return a copy of the project archive with one file replaced."""
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source, zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED
    ) as target:
        for entry in source.infolist():
            name = entry.filename.replace("\\", "/")
            if entry.is_dir():
                continue
            if name == path:
                target.writestr(name, new_text.encode("utf-8"))
            else:
                target.writestr(name, source.read(entry))
    return output.getvalue()


def write_fix(finding_id: str, archive: bytes) -> Path:
    target = storage_dir() / f"fix-{finding_id}.zip"
    target.write_bytes(archive)
    return target
