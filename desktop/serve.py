"""Serves the SentinelX application plus the phone-app (PWA) layer.

The website itself is untouched: this module imports the real FastAPI
application and adds manifest, service-worker, icons and a small head tag
injection so a phone can install the dashboard to its home screen.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.main import app  # the unmodified website application

WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"

HEAD_TAGS = (
    b'<link rel="manifest" href="/manifest.webmanifest">'
    b'<meta name="theme-color" content="#06080D">'
    b'<meta name="mobile-web-app-capable" content="yes">'
    b'<meta name="apple-mobile-web-app-capable" content="yes">'
    b'<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
    b'<link rel="apple-touch-icon" href="/pwa/icon-192.png">'
    b'<script src="/pwa/register.js" defer></script>'
)


class PwaHeadMiddleware(BaseHTTPMiddleware):
    """Injects the install tags into the served dashboard page only."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path not in ("/", "/admin", "/admin/"):
            return response
        if response.headers.get("content-type", "").split(";")[0] != "text/html":
            return response
        body = b""
        async for chunk in response.body_iterator:  # type: ignore[attr-defined]
            body += chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
        if b"</head>" in body and b"manifest.webmanifest" not in body:
            body = body.replace(b"</head>", HEAD_TAGS + b"</head>", 1)
        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in ("content-length", "content-type")
        }
        return Response(
            content=body,
            status_code=response.status_code,
            media_type="text/html",
            headers=headers,
        )


app.add_middleware(PwaHeadMiddleware)


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(
        WEBAPP_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(
        WEBAPP_DIR / "sw.js",
        media_type="text/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-store"},
    )


@app.get("/pwa/register.js", include_in_schema=False)
def register_script():
    return FileResponse(WEBAPP_DIR / "register.js", media_type="text/javascript")


@app.get("/pwa/icon-192.png", include_in_schema=False)
def icon_192():
    return FileResponse(WEBAPP_DIR / "icon-192.png", media_type="image/png")


@app.get("/pwa/icon-512.png", include_in_schema=False)
def icon_512():
    return FileResponse(WEBAPP_DIR / "icon-512.png", media_type="image/png")
