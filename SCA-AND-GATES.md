# Dependency scanning (SCA) and gate visibility

Two changes: the **SCA gate is now a real engine**, and failed analysis is
explained in the report instead of showing a bare `FAILED`.

## SCA — OSV advisory engine

The scanner reads pinned dependencies from manifests and resolves them against
the [OSV database](https://osv.dev):

| Manifest | Ecosystem |
| --- | --- |
| `requirements*.txt` (`pkg==1.2.3`) | PyPI |
| `package-lock.json` | npm |
| `go.mod` | Go |
| `pom.xml` (with property resolution) | Maven |

Each vulnerable package becomes a normal finding:

```
Vulnerable dependency: requests 2.19.1 (GHSA-9hjg-9r4m-mvj7)
severity: medium   path: requirements.txt
remediation: Upgrade requests to a release outside the affected range…
```

The gate then goes through the same policy engine as every other scanner:
findings → `PASS` / `WARN` / `BLOCK`. No manifests → still `NOT_CONFIGURED`.

**Fail closed:** if OSV cannot be reached, the gate becomes `FAILED` with the
note *"OSV advisory lookup failed; dependency coverage is unknown"* — never a
silent pass.

Report metadata records the engine, package count and lookup state under
`coverage.dependency_scan`.

### Limits (stated in the report)

- Direct, **pinned** versions only — ranges and unpinned entries are skipped.
- No transitive resolution, no lockfile integrity, no exploitability check.
- Queries go to `api.osv.dev`; nothing about your source is uploaded, only
  `name + version + ecosystem`.

## Gate visibility

`analysis_errors` (the files that broke Python/JS parsing) were stored but not
shown. They now appear at the top of **Coverage and limitations**:

```
app/legacy/server.py — Python parsing failed; SAST coverage incomplete
```

That is the difference between *"SAST FAILED"* and *"SAST FAILED because this
file"*.

## Verified

```
gate secrets PASS | 0 findings
gate sast    PASS | 0 findings
gate iac     PASS | 0 findings
gate sca     WARN | 18 findings | 2 pinned packages resolved against OSV
gate container NOT_CONFIGURED
gate dast      NOT_CONFIGURED
decision: BLOCK
coverage.dependency_scan = {"engine": "OSV", "packages": 2, "state": "ok"}
```

## Still not configured

- **container** — needs an image reference and a scanner (Trivy/Grype) plus a
  pulled image.
- **dast** — needs a running target and an authorised scanner (ZAP) with an
  agreed scope.

Both stay `NOT_CONFIGURED` and block the release, by design.

## Tests

`tests/test_sca.py` covers manifest parsing (PyPI, npm, Go, Maven), severity
mapping, the offline failure state and finding construction.
