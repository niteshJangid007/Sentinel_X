# SentinelX desktop + mobile app — one file

**`SentinelX-Desktop-Portable.exe`** (31 MB) contains the whole product:
the desktop dashboard **and** the installable phone app. Nothing is installed
on the target machine and no account or hosting is required.

## What the other person needs

| Requirement | Needed? |
| --- | --- |
| Python / Docker / PostgreSQL / Java | **No** — all bundled |
| Internet | Optional. Needed once for the public phone link; without it the app still runs locally |
| Windows 10/11 64-bit | Yes (for the desktop half) |
| Phone (Android or iPhone) | Optional, for the mobile app |

## Desktop

1. Copy the `.exe` to Desktop or Downloads (not inside this locked project
   folder) and double-click.
2. SmartScreen may ask once → **More info → Run anyway**.
3. It installs to `%LOCALAPPDATA%\SentinelX Desktop Portable` and opens the
   dashboard in a native window.

## Mobile app — installable, no store, no credits

At startup a **"Install SentinelX on your phone"** window appears with a QR code
and a public `https://…trycloudflare.com` address.

1. Scan the QR with the phone camera (works on **any network** — mobile data too).
2. Open the link in Chrome or Safari.
3. **Chrome:** menu → *Add to Home screen* / *Install app*.
   **Safari:** Share → *Add to Home Screen*.
4. The SentinelX icon appears on the home screen and opens **fullscreen**, with
   no browser bar — a real app experience, served by your PC.

The link is a Cloudflare quick tunnel: free, no account, revoked automatically
when the app closes. If the computer is offline, the window falls back to the
local Wi-Fi address (browser only, no install).

### What makes it installable

The app is served with a web app manifest, a service worker, theme colour and
icons — added at runtime by `desktop/serve.py` and `desktop/webapp/`. **The
website files themselves are untouched.**

## Where the data lives

- Database: `%LOCALAPPDATA%\SentinelX Desktop\sentinelx.db`
- Logs: `%LOCALAPPDATA%\SentinelX Desktop\logs\` (includes `tunnel.log`)
- Program: `%LOCALAPPDATA%\SentinelX Desktop Portable\`

Uninstall = delete those two folders.

## Verified on this machine

- Installer from Desktop → installed, local health `200`
- Public link created (`https://headed-intro-roots-bristol.trycloudflare.com`)
- `GET <public>/manifest.webmanifest` → **200** through Cloudflare
- Mobile window renders the QR, the public URL and the install steps
- Homepage served with `manifest` + `register.js` injected; `/sw.js` 200; icons 200
- Full scan flow on the portable runtime: 16 findings, BLOCK, risk 100

## Limits — say these out loud

- The public URL is temporary and dies with the app; anyone with the link can
  reach the login page (accounts and rate limiting still apply).
- Installing as an app requires the HTTPS link (browsers only install over
  HTTPS or localhost), which is why the tunnel exists.
- Offline mode installs nothing; the phone view then needs the same Wi-Fi.
- iOS and Android both work through the browser's install flow; there is no
  App Store / Play Store listing.
- Windows x64 desktop build; the phone side is platform-neutral.

## Rebuild

1. Embeddable Python 3.12 + `fastapi uvicorn httpx python-multipart pywebview
   pythonnet segno`, plus Tcl/Tk from a full Python install.
2. Copy `SentinelX\app` to `website\app`, the `SentinelX Desktop\desktop`
   package, `serve_entry.py`, and `cloudflared.exe`.
3. Add `portable.mode`, then wrap in a 7-Zip SFX (`7zSD.sfx`) whose
   `install.cmd` copies to `%LOCALAPPDATA%` and starts `pythonw`.

## Troubleshooting: phone says “Cannot reach the server”

1. **The link expires.** A quick-tunnel URL only works while that run of the
   desktop app is open. Always use the URL shown in the *current* QR window, not
   one from an earlier launch.
2. **Same Wi-Fi?** For the http://192.168.x.x:8000 address both devices must be
   on the same network. Guest Wi-Fi with client isolation blocks it.
3. **Firewall.** Run **Allow-Firewall.cmd as administrator** once (it is on the
   Desktop and next to the app). Without it Windows silently drops inbound
   connections from the phone.
4. **Server must be running.** The phone only mirrors the desktop app; if it is
   closed, nothing answers.
5. **Test in the phone browser first.** Paste the same URL into Chrome. If the
   browser also fails it is network/firewall; if the browser works but the app
   does not, tap ⋮ → Change server and re-enter the address.
