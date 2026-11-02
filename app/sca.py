"""Dependency vulnerability checks backed by the OSV database.

Only direct, pinned versions found in manifests are resolved. Network failure is
reported as a failed gate, never as a pass.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ElementTree

OSV_BATCH = "https://api.osv.dev/v1/querybatch"
MAX_PACKAGES = 400
TIMEOUT_SECONDS = 20

LIMITATION = (
    "Dependency checks resolve direct, pinned versions against the OSV database. "
    "Transitive dependencies, lockfile integrity and exploitability are not verified."
)

REQUIREMENT = re.compile(
    r"(?m)^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*==\s*([0-9][A-Za-z0-9.!+_-]*)\s*(?:#.*)?$"
)
GO_REQUIRE = re.compile(r"(?m)^\s*(?:require\s+)?([^\s()]+)\s+(v[0-9][^\s]*)\s*$")
SEVERITIES = {"critical", "high", "moderate", "medium", "low"}


def _pom_packages(text: str, path: str) -> list[dict]:
    packages: list[dict] = []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return packages
    namespace = {"m": "http://maven.apache.org/POM/4.0.0"}
    properties = {}
    for prop in root.findall(".//m:properties/*", namespace):
        properties[prop.tag.split("}")[-1]] = (prop.text or "").strip()
    for dependency in root.findall(".//m:dependencies/m:dependency", namespace):
        group = (dependency.findtext("m:groupId", default="", namespaces=namespace) or "").strip()
        artifact = (dependency.findtext("m:artifactId", default="", namespaces=namespace) or "").strip()
        version = (dependency.findtext("m:version", default="", namespaces=namespace) or "").strip()
        if version.startswith("${") and version.endswith("}"):
            version = properties.get(version[2:-1], "")
        if group and artifact and version and "${" not in version:
            packages.append(
                {
                    "name": f"{group}:{artifact}",
                    "version": version,
                    "ecosystem": "Maven",
                    "path": path,
                }
            )
    return packages


def collect(manifests: dict[str, str]) -> list[dict]:
    """Extract pinned dependencies from known manifest files."""
    packages: list[dict] = []
    for path, text in manifests.items():
        name = path.rsplit("/", 1)[-1].lower()
        if name.startswith("requirements") and name.endswith(".txt"):
            for match in REQUIREMENT.finditer(text):
                packages.append(
                    {
                        "name": match.group(1),
                        "version": match.group(2),
                        "ecosystem": "PyPI",
                        "path": path,
                    }
                )
        elif name == "package-lock.json":
            try:
                data = json.loads(text)
            except ValueError:
                continue
            for key, value in (data.get("packages") or {}).items():
                if not key or not isinstance(value, dict) or not value.get("version"):
                    continue
                package = value.get("name") or key.split("node_modules/")[-1]
                if package:
                    packages.append(
                        {
                            "name": package,
                            "version": value["version"],
                            "ecosystem": "npm",
                            "path": path,
                        }
                    )
            for package, value in (data.get("dependencies") or {}).items():
                if isinstance(value, dict) and value.get("version"):
                    packages.append(
                        {
                            "name": package,
                            "version": value["version"],
                            "ecosystem": "npm",
                            "path": path,
                        }
                    )
        elif name == "go.mod":
            for match in GO_REQUIRE.finditer(text):
                if match.group(2).startswith("v"):
                    packages.append(
                        {
                            "name": match.group(1),
                            "version": match.group(2),
                            "ecosystem": "Go",
                            "path": path,
                        }
                    )
        elif name == "pom.xml":
            packages.extend(_pom_packages(text, path))

    unique: dict[tuple, dict] = {}
    for package in packages:
        unique[(package["ecosystem"], package["name"], package["version"])] = package
    return list(unique.values())[:MAX_PACKAGES]


def severity_of(vulnerability: dict) -> str:
    data = vulnerability.get("database_specific") or {}
    value = str(data.get("severity") or "").lower()
    if value in SEVERITIES:
        return "medium" if value == "moderate" else value
    for entry in vulnerability.get("severity") or []:
        score = str(entry.get("score") or "")
        if score.upper().startswith("CVSS"):
            # Vector without a numeric base score: judge by impact metrics.
            return "high" if ("C:H" in score or "I:H" in score or "A:H" in score) else "medium"
        digits = re.search(r"^(\d+(?:\.\d+)?)$", score.strip())
        if digits:
            value = float(digits.group(1))
            if value >= 9.0:
                return "critical"
            if value >= 7.0:
                return "high"
            if value >= 4.0:
                return "medium"
            return "low"
    return "medium"


def _query(packages: list[dict]) -> list[dict]:
    payload = json.dumps(
        {
            "queries": [
                {"package": {"name": p["name"], "ecosystem": p["ecosystem"]}, "version": p["version"]}
                for p in packages
            ]
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OSV_BATCH,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "SentinelX/1.0"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8")).get("results") or []


def scan(packages: list[dict], finding_factory) -> dict:
    """Return findings and the state of the SCA engine."""
    if not packages:
        return {"findings": [], "state": "empty", "packages": 0, "note": ""}
    try:
        results = _query(packages)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return {
            "findings": [],
            "state": "failed",
            "packages": len(packages),
            "note": "OSV advisory lookup failed; dependency coverage is unknown",
        }

    findings = []
    seen = set()
    for package, result in zip(packages, results):
        for vulnerability in (result.get("vulns") or [])[:20]:
            identifier = vulnerability.get("id") or "OSV"
            key = (package["path"], package["name"], identifier)
            if key in seen:
                continue
            seen.add(key)
            summary = (vulnerability.get("summary") or "Known vulnerability").strip()
            findings.append(
                finding_factory(
                    f"Vulnerable dependency: {package['name']} {package['version']} ({identifier})",
                    severity_of(vulnerability),
                    "sca",
                    package["path"],
                    None,
                    f"{summary} Reported by OSV for {package['ecosystem']}.",
                    f"Upgrade {package['name']} to a release outside the affected range; review {identifier}.",
                    None,
                )
            )
    return {
        "findings": findings,
        "state": "ok",
        "packages": len(packages),
        "note": f"{len(packages)} pinned packages resolved against OSV",
    }
