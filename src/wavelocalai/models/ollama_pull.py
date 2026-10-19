"""Téléchargement d'un modèle par Ollama (`POST /api/pull`, flux NDJSON) : seul appel de la v2 qui
télécharge un modèle (AD-17). Jamais lancé par une route de lecture, ni au démarrage : seul le
service d'installation l'appelle, sur un clic.

Ollama répond par des lignes JSON : `{"status": "pulling manifest"}`, puis une ligne par couche
`{"status": "pulling <empreinte>", "digest", "total", "completed"}`, puis `verifying sha256 digest`,
`writing manifest`, `success`. Une ligne `{"error": "..."}` dit l'échec (nom inconnu, disque plein).
`pull_updates` agrège les couches en un seul total d'octets et rend des `PullUpdate` ; la fin
normale est la ligne `success`. Une panne lève `PullError(cause)`, `cause` parmi `not_found` (le
nom n'existe pas), `ollama_down` (Ollama ne répond plus ou a fermé le flux) et `interrupted` (autre
refus d'Ollama, disque plein par exemple), la liste fermée de `pull_failed`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

# Silence maximal d'Ollama : la vérification d'une grosse couche ne publie rien pendant un moment.
READ_TIMEOUT_S = 120.0
NOT_FOUND_MARKERS = ("file does not exist", "not found", "manifest unknown", "does not exist")


class PullError(Exception):
    """L'installation a échoué : `cause` est `not_found`, `ollama_down` ou `interrupted`."""

    def __init__(self, cause: str, technical: str) -> None:
        super().__init__(technical)
        self.cause = cause
        self.technical = technical


@dataclass(frozen=True)
class PullUpdate:
    """État du téléchargement : `phase` parmi `preparing`, `downloading`, `verifying` ; les octets
    sont ceux de toutes les couches connues (`total_bytes` nul tant qu'aucune n'est annoncée)."""

    phase: str
    received_bytes: int = 0
    total_bytes: int = 0
    done: bool = False  # ligne `success`


def _count(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _is_not_found(message: str) -> bool:
    text = message.lower()
    return any(marker in text for marker in NOT_FOUND_MARKERS)


class Layers:
    """Octets reçus et totaux de chaque couche, additionnés : le total ne baisse jamais (une
    couche déjà complète garde le sien quand Ollama ne la ré-annonce pas)."""

    def __init__(self) -> None:
        self._total: dict[str, int] = {}
        self._done: dict[str, int] = {}

    def update(self, digest: str, total: int, completed: int) -> None:
        if total > 0:
            self._total[digest] = total
        self._done[digest] = min(completed, self._total.get(digest, completed))

    @property
    def total(self) -> int:
        return sum(self._total.values())

    @property
    def received(self) -> int:
        return sum(self._done.values())


def parse_line(line: dict, layers: Layers) -> PullUpdate | None:
    """Mise à jour de l'état d'une ligne du flux ; `None` pour une ligne sans effet. Une ligne
    `error` lève `PullError`."""
    error = line.get("error")
    if error:
        message = str(error)
        raise PullError("not_found" if _is_not_found(message) else "interrupted", message)
    status = str(line.get("status") or "")
    if status == "success":
        return PullUpdate("verifying", layers.received, layers.total, done=True)
    digest = line.get("digest")
    if isinstance(digest, str) and digest and status.startswith("pulling"):
        layers.update(digest, _count(line.get("total")), _count(line.get("completed")))
        return PullUpdate("downloading", layers.received, layers.total)
    if status.startswith("pulling"):  # « pulling manifest »
        return PullUpdate("preparing", layers.received, layers.total)
    if status:  # « verifying sha256 digest », « writing manifest », « removing any unused layers »
        return PullUpdate("verifying", layers.received, layers.total)
    return None


async def pull_updates(
    host: str,
    tag: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    read_timeout_s: float = READ_TIMEOUT_S,
) -> AsyncIterator[PullUpdate]:
    """Suit l'installation de `tag` jusqu'à `success`. Lève `PullError`."""
    layers = Layers()
    timeout = httpx.Timeout(connect=2.0, read=read_timeout_s, write=10.0, pool=10.0)
    try:
        async with (
            httpx.AsyncClient(
                base_url=host.rstrip("/"),
                timeout=timeout,
                transport=transport,
                trust_env=False,  # pas de proxy système pour une adresse locale
            ) as client,
            client.stream("POST", "/api/pull", json={"model": tag, "stream": True}) as response,
        ):
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", "replace").strip()
                missing = response.status_code == 404 or _is_not_found(body)
                raise PullError(
                    "not_found" if missing else "interrupted",
                    f"POST /api/pull : HTTP {response.status_code}, {body[:300]}",
                )
            async for raw in response.aiter_lines():
                if not raw.strip():
                    continue
                try:
                    line = json.loads(raw)
                except ValueError:
                    continue  # une ligne illisible n'arrête pas le téléchargement
                if not isinstance(line, dict):
                    continue
                update = parse_line(line, layers)
                if update is None:
                    continue
                yield update
                if update.done:
                    return
    except PullError:
        raise
    except (httpx.TransportError, OSError) as exc:
        raise PullError("ollama_down", f"{type(exc).__name__} : {exc}") from exc
    raise PullError("ollama_down", "flux /api/pull fermé par Ollama sans `success`")
