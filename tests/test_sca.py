"""Dependency scanning: manifest parsing, severity mapping and fail-closed lookup."""

import json

import pytest

from app import sca

pytestmark = pytest.mark.unit


def test_requirements_pins_are_collected():
    packages = sca.collect({"requirements.txt": "flask==2.0.0\nrequests==2.19.1\n# note\nunpinned\n"})
    assert {(p["ecosystem"], p["name"], p["version"]) for p in packages} == {
        ("PyPI", "flask", "2.0.0"),
        ("PyPI", "requests", "2.19.1"),
    }


def test_package_lock_and_go_mod_are_collected():
    lock = json.dumps({"packages": {"node_modules/lodash": {"version": "4.17.4"}}})
    packages = sca.collect(
        {
            "package-lock.json": lock,
            "go.mod": "module demo\n\nrequire github.com/gin-gonic/gin v1.6.0\n",
        }
    )
    assert ("npm", "lodash", "4.17.4") in {(p["ecosystem"], p["name"], p["version"]) for p in packages}
    assert ("Go", "github.com/gin-gonic/gin", "v1.6.0") in {
        (p["ecosystem"], p["name"], p["version"]) for p in packages
    }


def test_maven_pom_versions_are_collected():
    pom = (
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><dependencies><dependency>'
        "<groupId>org.apache.logging.log4j</groupId><artifactId>log4j-core</artifactId>"
        "<version>2.14.1</version></dependency></dependencies></project>"
    )
    packages = sca.collect({"pom.xml": pom})
    assert packages[0]["name"] == "org.apache.logging.log4j:log4j-core"
    assert packages[0]["ecosystem"] == "Maven"


def test_severity_prefers_database_value_then_cvss():
    assert sca.severity_of({"database_specific": {"severity": "MODERATE"}}) == "medium"
    assert sca.severity_of({"database_specific": {"severity": "CRITICAL"}}) == "critical"
    vector = {"severity": [{"score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}]}
    assert sca.severity_of(vector) == "high"
    assert sca.severity_of({"severity": [{"score": "9.8"}]}) == "critical"


def test_no_manifests_reports_empty_state():
    result = sca.scan([], lambda *args, **kwargs: pytest.fail("no lookup expected"))
    assert result["state"] == "empty"
    assert result["findings"] == []


def test_network_failure_is_a_failed_state(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(sca, "_query", boom)
    result = sca.scan([{"name": "requests", "version": "2.19.1", "ecosystem": "PyPI", "path": "requirements.txt"}], None)
    assert result["state"] == "failed"
    assert result["findings"] == []
    assert "unknown" in result["note"]


def test_osv_results_become_findings(monkeypatch):
    def fake_query(packages):
        return [{"vulns": [{"id": "GHSA-test", "summary": "Demo vulnerability", "database_specific": {"severity": "HIGH"}}]}]

    monkeypatch.setattr(sca, "_query", fake_query)

    def factory(title, severity, scanner, path, line, description, remediation, cwe=None):
        return {
            "title": title,
            "severity": severity,
            "scanner": scanner,
            "path": path,
            "line": line,
            "description": description,
            "remediation": remediation,
            "cwe": cwe,
        }

    result = sca.scan(
        [{"name": "lodash", "version": "4.17.4", "ecosystem": "npm", "path": "package-lock.json"}],
        factory,
    )
    assert result["state"] == "ok"
    finding = result["findings"][0]
    assert finding["scanner"] == "sca"
    assert finding["severity"] == "high"
    assert "GHSA-test" in finding["title"]
    assert finding["path"] == "package-lock.json"
