"""Coquille du front : `GET /` rend `index.html`, `/static/` sert les fichiers (AD-4, AD-19, AD-20).

Aucune dépendance JS tierce hors `static/vendor/`, aucun CDN : la politique de contenu ci-dessous
fait refuser au navigateur toute ressource qui ne vient pas de la même origine. `no-cache` : le
navigateur revalide à chaque fois (ETag, 304), donc une mise à jour de l'app se voit sans vider
le cache.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Windows lit les types dans le registre : un `.js` y est parfois `text/plain`, que le navigateur
# refuse pour un module ES. On fixe ceux dont le front dépend.
for _extension, _media_type in {
    ".js": "text/javascript",
    ".mjs": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".woff2": "font/woff2",
    ".html": "text/html",
}.items():
    mimetypes.add_type(_media_type, _extension)

CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)

STATIC_HEADERS = {
    "Cache-Control": "no-cache",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


class ShellStaticFiles(StaticFiles):
    """`StaticFiles` qui ajoute les en-têtes de `STATIC_HEADERS` (réponses 200 et 304)."""

    def file_response(self, *args: Any, **kwargs: Any):  # type: ignore[no-untyped-def]
        response = super().file_response(*args, **kwargs)
        response.headers.update(STATIC_HEADERS)
        return response


def mount_shell(app: FastAPI, static_dir: Path = STATIC_DIR) -> None:
    """Pose la page d'accueil (`/`) et les fichiers statiques (`/static/`) sur l'application."""

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(
            static_dir / "index.html",
            media_type="text/html; charset=utf-8",
            headers=STATIC_HEADERS,
        )

    app.mount("/static", ShellStaticFiles(directory=static_dir), name="static")
