# SentinelX demo kit

Everything needed for the live demo.

## Files

- `sentinelx-demo-app.zip` — a deliberately vulnerable sample project used for
  the scan. Upload it from the dashboard (**Upload ZIP**), no internet needed.
- `demo-app/` — the same files, unpacked, so you can show the code on screen.

## What the scan reports

16 findings, risk score 100, decision **BLOCK**:

| Severity | Example finding | File |
| --- | --- | --- |
| Critical | Private key material | `.env` |
| High | Potential AWS access key | `.env` |
| High | Potential GitHub access token | `.env` |
| High | Hardcoded credentials (3×) | `config/settings.py` |
| High | Command execution / shell=True | `app.py` |
| High | Unsafe deserialization | `app.py` |
| High | Dynamic code execution (`eval`) | `app.py` |
| High | Privileged container | `docker-compose.yml` |
| Medium | Docker image runs as root | `Dockerfile` |
| Medium | Dynamic HTML writes (3×) | `static/app.js`, `templates/index.html` |
| Medium | Client-side permission decision | `static/app.js` |

Gates: `secrets BLOCK`, `sast BLOCK`, `iac BLOCK`, and deliberately
`sca / container / dast = NOT_CONFIGURED` — the product reports what it did
**not** check instead of pretending a clean pass.

## Reset between rehearsals

The demo is repeatable: every scan is a new record. If you want a clean
dashboard, delete the demo project and create it again (or use a fresh account).
