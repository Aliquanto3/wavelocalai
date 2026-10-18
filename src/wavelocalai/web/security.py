"""Sécurité de l'API locale (AD-19) : un site visité ne doit pas piloter le serveur.

- `Host` hors `127.0.0.1:<port>` / `localhost:<port>` refusé (DNS rebinding) ;
- écriture (`POST`, `PUT`, `PATCH`, `DELETE`) dont l'`Origin` n'est pas celle de la page servie
  refusée (CSRF) ; une requête sans `Origin` (curl, tests) passe ;
- aucun en-tête CORS n'est jamais émis : ce module n'en ajoute pas, et rien d'autre non plus.

Middleware ASGI pur (pas `BaseHTTPMiddleware`) pour ne pas gêner les flux SSE.
"""

from __future__ import annotations

from collections.abc import Iterable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from wavelocalai.errors import ERRORS, build_envelope

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def allowed_hosts(port: int) -> frozenset[str]:
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})


class LocalOnlyMiddleware:
    def __init__(self, app: ASGIApp, port: int, secrets: Iterable[str] = ()) -> None:
        self.app = app
        self._hosts = allowed_hosts(port)
        self._secrets = tuple(secrets)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        refusal: tuple[str, dict[str, str]] | None = None
        if host.lower() not in self._hosts:
            refusal = ("forbidden_host", {"host": host})
        elif scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            origin = headers.get("origin")
            if origin is not None and origin.lower() != f"http://{host.lower()}":
                refusal = ("forbidden_origin", {"origin": origin})
        if refusal is None:
            await self.app(scope, receive, send)
            return
        code, detail = refusal
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        envelope = build_envelope(code, secrets=self._secrets, **detail)
        response = JSONResponse(envelope, status_code=ERRORS[code].status)
        await response(scope, receive, send)
