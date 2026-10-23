"""Découverte des routes de l'application, commune aux tests de budget (AD-15) et de paramètres.

Aucune classe interne de FastAPI n'est importée : les routes d'un `include_router` sont lues par
leurs attributs (`original_router`, `include_context.prefix`), et `Mount` est la classe publique
de Starlette. Un test de recoupement avec `app.openapi()` (API publique) échoue bruyamment si une
montée de version de FastAPI change cette structure : mieux vaut un test rouge qu'une route
oubliée (C2, C3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.sse import EventSourceResponse
from starlette.routing import Mount

PATH_PARAM = re.compile(r"{([^}:]+)(?::[^}]*)?}")


@dataclass(frozen=True)
class RouteInfo:
    """Une route servie : méthodes, chemin complet, flux SSE ou non, paramètres de requête."""

    path: str
    methods: frozenset[str]
    streams: bool = False
    hidden: bool = False  # `include_in_schema=False`
    query: tuple[str, ...] = field(default=())

    @property
    def path_params(self) -> tuple[str, ...]:
        return tuple(PATH_PARAM.findall(self.path))


@dataclass(frozen=True)
class StaticMount:
    """Un `Mount` qui sert des fichiers d'un dossier (`StaticFiles`)."""

    prefix: str
    directory: Path


def _plain(path: str) -> str:
    """Chemin sans convertisseur (`{tag:path}` devient `{tag}`), comme dans le schéma OpenAPI."""
    return PATH_PARAM.sub(lambda match: "{" + match.group(1) + "}", path)


def _streams(route: Any) -> bool:
    response_class = getattr(route, "response_class", None)
    response_class = getattr(response_class, "value", response_class)  # valeur par défaut FastAPI
    return isinstance(response_class, type) and issubclass(response_class, EventSourceResponse)


def _query_names(route: Any) -> tuple[str, ...]:
    dependant = getattr(route, "dependant", None)
    return tuple(p.name for p in getattr(dependant, "query_params", ()) or ())


def _walk(routes: Any, prefix: str, found: list[RouteInfo], mounts: list[StaticMount]) -> None:
    for route in routes:
        if isinstance(route, Mount):
            _walk_mount(route, prefix, found, mounts)
        elif getattr(route, "path", None) is not None and getattr(route, "methods", None):
            found.append(
                RouteInfo(
                    path=_plain(prefix + route.path),
                    methods=frozenset(route.methods),
                    streams=_streams(route),
                    hidden=not getattr(route, "include_in_schema", True),
                    query=_query_names(route),
                )
            )
        elif (original := getattr(route, "original_router", None)) is not None:
            # Routes d'un `include_router` : rangées derrière l'enveloppe, préfixe à part.
            extra = getattr(getattr(route, "include_context", None), "prefix", "") or ""
            _walk(original.routes, prefix + extra, found, mounts)
        else:
            # WebSocket, route sans méthode ou structure nouvelle : ni le budget ni le contrôle des
            # paramètres ne la couvriraient. Mieux vaut un test rouge qu'une route oubliée.
            raise AssertionError(
                f"route non couverte ({type(route).__name__} "
                f"{getattr(route, 'path', '?')!r}) : adapter route_discovery.py"
            )


def _walk_mount(mount: Mount, prefix: str, found: list[RouteInfo], mounts: list[StaticMount]):
    directory = getattr(mount.app, "directory", None)
    if directory is not None:
        mounts.append(StaticMount(prefix + mount.path, Path(directory)))
    elif mount.routes:
        _walk(mount.routes, prefix + mount.path, found, mounts)
    else:
        raise AssertionError(f"Mount {mount.path!r} ni de fichiers ni de routes : non mesurable")


def discover(app: FastAPI) -> tuple[list[RouteInfo], list[StaticMount]]:
    """Toutes les routes (dans un routeur inclus ou non, hors schéma comprises) et les `Mount`."""
    found: list[RouteInfo] = []
    mounts: list[StaticMount] = []
    _walk(app.routes, "", found, mounts)
    documented = app.openapi()["paths"]
    # Les flux SSE sont déclarés dans le schéma par leur type de contenu : plus sûr que la classe.
    out: list[RouteInfo] = []
    for info in found:
        operations = documented.get(info.path, {})
        streams = info.streams or any(
            "text/event-stream" in response.get("content", {})
            for operation in operations.values()
            for response in operation.get("responses", {}).values()
        )
        out.append(
            RouteInfo(info.path, info.methods, streams, info.hidden, info.query)
            if streams != info.streams
            else info
        )
    return out, mounts


def read_paths(app: FastAPI) -> list[str]:
    """Chemins `GET` sans paramètre de chemin, hors flux SSE, y compris hors schéma."""
    routes, _ = discover(app)
    return sorted(
        {r.path for r in routes if "GET" in r.methods and not r.streams and "{" not in r.path}
    )


def static_samples(mount: StaticMount, per_extension: int = 1, largest: int = 3) -> list[str]:
    """Quelques fichiers d'un `Mount` de fichiers : les plus gros, et un par extension.

    Tout mesurer coûterait des centaines d'applications neuves pour un résultat identique : un
    fichier statique ne touche ni la base ni Ollama.
    """
    files = sorted(
        (p for p in mount.directory.rglob("*") if p.is_file()),
        key=lambda p: (-p.stat().st_size, p.as_posix()),
    )
    chosen: list[Path] = files[:largest]
    seen: dict[str, int] = {}
    for file in files:
        seen[file.suffix] = seen.get(file.suffix, 0) + 1
        if seen[file.suffix] <= per_extension and file not in chosen:
            chosen.append(file)
    return sorted(
        mount.prefix.rstrip("/") + "/" + p.relative_to(mount.directory).as_posix() for p in chosen
    )
