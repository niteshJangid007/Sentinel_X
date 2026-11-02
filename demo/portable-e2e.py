"""End-to-end check of the portable build through the real HTTP API."""

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8099"
ZIP = r"D:\SentinelX-backend - Copy\demo\sentinelx-demo-app.zip"


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30.0)
    email = f"portable{int(time.time())}@example.com"
    password = "PortablePass123!"

    response = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    print("register:", response.status_code)
    if response.status_code != 201:
        print(response.text[:300])
        return 1

    headers = {"origin": BASE, "sec-fetch-site": "same-origin"}
    response = client.post("/api/v1/projects", json={"name": "Portable Demo"}, headers=headers)
    print("project:", response.status_code)
    project = response.json()

    with open(ZIP, "rb") as handle:
        files = {"file": ("sentinelx-demo-app.zip", handle, "application/zip")}
        response = client.post(
            f"/api/v1/projects/{project['id']}/upload", files=files, headers=headers
        )
    print("upload:", response.status_code)
    scan = response.json()
    scan_id = scan["id"]

    for _ in range(60):
        time.sleep(1)
        current = client.get(f"/api/v1/scans/{scan_id}").json()
        if current["status"] in ("completed", "failed"):
            break

    findings = client.get(f"/api/v1/findings?project_id={project['id']}").json()
    report = client.get(f"/api/v1/scans/{scan_id}/report")
    print("scan status:", current["status"])
    print("decision:", current.get("decision"), "| risk:", current.get("risk_score"))
    print("gates:", [(g["name"], g["status"]) for g in current.get("gates", [])])
    print("findings:", len(findings))
    print("report:", report.status_code)
    severities = {}
    for finding in findings:
        severities[finding["severity"]] = severities.get(finding["severity"], 0) + 1
    print("severity:", severities)
    ok = (
        current["status"] == "completed"
        and current.get("decision") == "BLOCK"
        and len(findings) == 16
        and report.status_code == 200
    )
    print("PORTABLE E2E:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
