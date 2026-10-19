"""Coquille du front : `GET /` rend `index.html`, `/static/` sert les fichiers (AD-4, AD-19, AD-20).

Aucune dépendance JS tierce hors `static/vendor/`, aucun CDN : la politique de contenu ci-dessous
fait refuser au navigateur toute ressource qui ne vient pas de la même origine. `no-cache` : le
navigateur revalide à chaque fois (ETag, 304), donc une mise à jour de l'app se voit sans vider
le cache.
"""

from __future__ import annotations

import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
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


# Imports de modules JS : `from "./x.js"` / `import "./x.js"` (statiques), `import("./x.js")` (dynamique).
_STATIC_IMPORT_RE = re.compile(r"""(?:\bfrom\s*|\bimport\s*)["'](\.{1,2}/[^"']+\.js)["']""")
_DYNAMIC_IMPORT_RE = re.compile(r"""\bimport\(\s*["'](\.{1,2}/[^"']+\.js)["']""")
_PRELOAD_RE = re.compile(r'<link rel="modulepreload" href="(/static/[^"]+)">')


def text_catalog(static_dir: Path) -> dict[str, Any]:
    """Les textes de `i18n/fr/*.json` en un seul document, sous les mêmes clés que le catalogue.

    Les fichiers par écran restent la source ; une clé de premier niveau déclarée dans deux
    fichiers lève une erreur (jamais d'écrasement silencieux).
    """
    merged: dict[str, Any] = {}
    for path in sorted((static_dir / "i18n" / "fr").glob("*.json")):
        part = json.loads(path.read_text(encoding="utf-8"))
        for key in part:
            if key in merged:
                raise ValueError(f"Clé de textes déclarée deux fois : {key} ({path.name}).")
            merged[key] = part[key]
    return merged


def module_graph(static_dir: Path, entries: list[str]) -> list[str]:
    """Les modules joignables depuis `entries` (chemins `/static/...`), dans l'ordre de découverte.

    Suit les imports statiques, et les `import("./x.js")` littéraux de `main.js` seul (ceux du
    routeur chargent les écrans à la demande, hors du chemin de rendu) ; un fichier absent est
    ignoré. Sert à précharger d'un coup ce que le navigateur découvrirait
    sinon de saut en saut (AD-15).
    """
    seen: list[str] = []
    queue = list(entries)
    while queue:
        url = queue.pop(0)
        if url in seen:
            continue
        path = static_dir / url.removeprefix("/static/")
        if not path.is_file():
            continue
        seen.append(url)
        base = url.rsplit("/", 1)[0]
        source = path.read_text(encoding="utf-8")
        targets = _STATIC_IMPORT_RE.findall(source)
        if url == "/static/main.js":
            targets += _DYNAMIC_IMPORT_RE.findall(source)
        for target in targets:
            parts: list[str] = []
            for part in f"{base}/{target}".split("/"):
                if part == "..":
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            queue.append("/".join(parts))
    return seen


def render_index(static_dir: Path) -> str:
    """`index.html` avec le document de textes et chaque module de la coquille non déjà listé préchargés.

    Le fichier reste la source (ses liens sont les points d'entrée) ; le serveur ajoute le reste
    du graphe des imports de `main.js`, pour que la coquille ne descende pas ce graphe en cascade
    de requêtes (budget de rendu, AD-15). Les écrans chargés à la demande n'y sont pas.
    """
    html = (static_dir / "index.html").read_text(encoding="utf-8")
    listed = _PRELOAD_RE.findall(html)
    entries = ["/static/main.js", *listed]
    extra = [url for url in module_graph(static_dir, entries) if url not in listed]
    if not extra:
        return html
    links = "".join(f'  <link rel="modulepreload" href="{url}">\n' for url in extra)
    marker = '  <script type="module"'
    return html.replace(marker, links + marker, 1)


def mount_shell(app: FastAPI, static_dir: Path = STATIC_DIR) -> None:
    """Pose la page d'accueil (`/`) et les fichiers statiques (`/static/`) sur l'application."""

    # Assemblés une fois au démarrage : les fichiers sources ne changent pas pendant l'exécution.
    index_html = render_index(static_dir)
    catalog = text_catalog(static_dir)

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse(index_html, headers=STATIC_HEADERS)

    @app.get("/static/i18n/fr.json", include_in_schema=False)
    async def texts() -> JSONResponse:
        return JSONResponse(catalog, headers=STATIC_HEADERS)

    app.mount("/static", ShellStaticFiles(directory=static_dir), name="static")
