"""Auto-fix proposals: deterministic, reviewed and never silent."""

import io
import zipfile

import pytest

from app import remediation

DOCKERFILE_WITH_ROOT = "FROM python:3.12-slim\nWORKDIR /app\nUSER root\nCMD [\"python\", \"app.py\"]\n"
COMPOSE_PRIVILEGED = "services:\n  api:\n    image: demo\n    privileged: true\n"
JS_INNER_HTML = "const node = document.getElementById('out');\nnode.innerHTML = location.hash;\n"


def finding(title, path="Dockerfile", line=3):
    return {"id": "f1", "title": title, "path": path, "line": line, "scanner": "iac"}


def test_dockerfile_root_is_replaced_with_numeric_user():
    proposal = remediation.propose(finding("Docker image runs as root"), {"Dockerfile": DOCKERFILE_WITH_ROOT.encode()})
    assert proposal["available"] is True
    assert "USER 10001" in proposal["after"]
    assert "USER root" in proposal["diff"] and "USER 10001" in proposal["diff"]


def test_privileged_container_is_disabled():
    proposal = remediation.propose(
        finding("Privileged container configuration", "docker-compose.yml", 4),
        {"docker-compose.yml": COMPOSE_PRIVILEGED.encode()},
    )
    assert proposal["available"] is True
    assert "privileged: false" in proposal["after"]


def test_inner_html_becomes_text_content():
    proposal = remediation.propose(
        finding("Dynamic HTML write requires injection review", "static/app.js", 2),
        {"static/app.js": JS_INNER_HTML.encode()},
    )
    assert proposal["available"] is True
    assert ".textContent =" in proposal["after"]
    assert ".innerHTML =" not in proposal["after"]


def test_unknown_finding_offers_no_automatic_fix():
    proposal = remediation.propose(
        finding("Private key material", ".env", 7), {".env": b"KEY=secret\n"}
    )
    assert proposal["available"] is False
    assert "No automated fix" in proposal["reason"]


def test_missing_file_offers_no_fix():
    proposal = remediation.propose(finding("Docker image runs as root"), {})
    assert proposal["available"] is False


def test_patched_archive_replaces_only_the_target_file():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Dockerfile", DOCKERFILE_WITH_ROOT)
        archive.writestr("app.py", "print('hello')\n")
    original = buffer.getvalue()

    patched = remediation.patched_archive(original, "Dockerfile", DOCKERFILE_WITH_ROOT.replace("root", "10001"))

    with zipfile.ZipFile(io.BytesIO(patched)) as archive:
        assert "USER 10001" in archive.read("Dockerfile").decode()
        assert archive.read("app.py").decode() == "print('hello')\n"
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        assert "USER root" in archive.read("Dockerfile").decode()


pytestmark = pytest.mark.unit
