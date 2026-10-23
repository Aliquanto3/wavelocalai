"""Routes de l'Arène : lancer, lister, exporter, effacer (AD-5, AD-13).

- `POST /api/arena/runs` : lance une comparaison de 2 à 4 modèles, rend `{run_id}` aussitôt. Le flux
  se lit par `GET /api/runs/{id}/events` (AD-6). L'Arène n'ouvre pas de conversation : la réponse ne
  porte pas de `conversation_id`.
- `GET /api/arena/runs` : les comparaisons les plus récentes d'abord, de quoi les rouvrir par
  `#/arene/comparer/<run_id>` (story 3.6).
- `GET /api/arena/runs/{id}.csv` et `.md` : export en pièce jointe avec la preuve de la mesure.
- `DELETE /api/arena/runs/{id}` : efface le texte (`run_events`, `messages`), garde les lignes `runs`
  comme registre carbone ; `409 arena_busy` si l'Arène est active. Le hub écrit, rien ici.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from wavelocalai.config import get_version
from wavelocalai.errors import AppError
from wavelocalai.inference.arena import ArenaCommand, ArenaService
from wavelocalai.runs.arena_export import export_document, to_csv, to_markdown
from wavelocalai.runs.snapshot import arena_record, list_arena_runs, run_snapshot
from wavelocalai.store.db import utc_now_iso

logger = logging.getLogger("wavelocalai.web")

router = APIRouter(prefix="/api")

MAX_PROMPT_CHARS = 100_000


class ArenaBody(BaseModel):
    models: list[str]  # 2 à 4 modèles distincts : vérifié par le service, qui résout les tags
    prompt: str = Field(max_length=MAX_PROMPT_CHARS)
    judge: str | None = None
    criteria: list[str] = Field(default_factory=list)
    allow_cloud: bool = False

    @field_validator("prompt")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("la question est vide")
        return value


class ArenaStarted(BaseModel):
    run_id: str


@router.post("/arena/runs")
async def start_arena_run(body: ArenaBody, request: Request) -> ArenaStarted:
    service: ArenaService | None = request.app.state.arena
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service de l'Arène n'est pas démarré.")
    handle = await service.start(ArenaCommand(**body.model_dump()))
    return ArenaStarted(run_id=handle.run_id)


@router.get("/arena/runs")
async def arena_runs(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> dict[str, Any]:
    store = request.app.state.store
    if store is None:  # hors du cycle de vie : rien à lister
        return {"runs": []}
    return {"runs": await list_arena_runs(store, limit)}


async def _evidence(request: Request) -> dict[str, Any]:
    """La preuve de la mesure qui ne vient pas du run : fiche machine, version d'Ollama (celle que la
    sonde a vue en dernier) et digest de chaque modèle connu du registre. Au mieux : un registre ou
    une fiche en peine donne `None`, jamais une valeur inventée."""
    app = request.app
    try:
        machine = await app.state.system_sampler.identity()
    except Exception:  # noqa: BLE001 - l'export ne dépend pas de la fiche
        logger.warning("Fiche machine indisponible pour l'export", exc_info=True)
        machine = None
    try:
        listed = await app.state.registry.list_models(allow_cloud=True)
        digests = {model.tag: model.digest for model in listed.models}
    except Exception:  # noqa: BLE001
        logger.warning("Liste des modèles indisponible pour l'export", exc_info=True)
        digests = {}
    return {"machine": machine, "digests": digests}


async def _export(run_id: str, request: Request) -> dict[str, Any]:
    store = request.app.state.store
    if store is None:
        raise AppError("internal", "La base n'est pas ouverte.")
    settings = request.app.state.settings
    snapshot = await run_snapshot(store, run_id, settings.cloud.prices)
    if snapshot is None or snapshot["kind"] != "arena":
        raise AppError("run_not_found", f"Arène {run_id} inconnue.", run_id=run_id)
    if snapshot["status"] in ("running", "awaiting_approval"):
        raise AppError("arena_busy", "L'Arène est active.", run_id=run_id)
    if snapshot["erased"]:  # AD-13 : plus de texte ni de notes, rien à exporter
        raise AppError("run_not_found", f"Arène {run_id} effacée.", run_id=run_id)
    return export_document(
        snapshot,
        await arena_record(store, run_id),
        await _evidence(request),
        utc_now_iso(),
        get_version(),
        settings.secret_values(),
    )


def _attachment(body: str, media_type: str, run_id: str, extension: str) -> Response:
    return Response(
        body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="arene-{run_id[:8]}.{extension}"'},
    )


# Les exports d'abord : `{run_id}` seul accepterait aussi « abc.csv ».
@router.get("/arena/runs/{run_id}.csv")
async def export_csv(run_id: str, request: Request) -> Response:
    return _attachment(
        to_csv(await _export(run_id, request)), "text/csv; charset=utf-8", run_id, "csv"
    )


@router.get("/arena/runs/{run_id}.md")
async def export_markdown(run_id: str, request: Request) -> Response:
    return _attachment(
        to_markdown(await _export(run_id, request)), "text/markdown; charset=utf-8", run_id, "md"
    )


@router.delete("/arena/runs/{run_id}", status_code=204)
async def delete_arena_run(run_id: str, request: Request) -> Response:
    hub = request.app.state.hub
    if hub is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le hub des runs n'est pas démarré.")
    await hub.erase_arena(run_id)
    return Response(status_code=204)
