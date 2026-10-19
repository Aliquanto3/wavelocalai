"""Routes de l'évaluation de la qualité d'une réponse documentaire (story 7.1, AD-5, AD-13).

- `POST /api/rag/eval/runs` : lance l'évaluation de 1 à 4 modèles sur une question ou un jeu de
  questions, et rend `{run_id}` aussitôt. Les extraits sont cherchés une fois dans la base et donnés
  tels quels à tous les modèles ; le juge note la fidélité, la pertinence et la précision du contexte.
  Le flux se lit par `GET /api/runs/{id}/events` (`eval_metric`, AD-6), le résultat et sa version
  partielle par `GET /api/runs/{id}` (`partial`). Plus de 4 modèles : `422 invalid_request`.
- `GET /api/rag/eval/runs?limit=` : les évaluations passées, les plus récentes d'abord, sans les
  évaluations effacées (décision n° 14, pour la story 7.3).
- `DELETE /api/rag/eval/runs/{id}` : efface les notes et le texte (`evaluations`, `run_events`) et
  garde les lignes `runs` comme registre carbone ; `409 run_busy` si l'évaluation est active. Le hub
  écrit, rien ici.

Toute la logique est dans `evaluation/` ; `build_service` n'est que le câblage de l'application.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator

from wavelocalai.errors import AppError
from wavelocalai.evaluation.judge import Judge
from wavelocalai.evaluation.service import (
    MAX_QUESTION_CHARS,
    MAX_QUESTIONS,
    EvalCommand,
    EvaluationService,
)
from wavelocalai.inference.streaming import Guard
from wavelocalai.models.factory import ModelFactory
from wavelocalai.rag.eval_base import EvalRetrieval
from wavelocalai.rag.index import VectorIndex
from wavelocalai.runs.eval_snapshot import list_eval_runs
from wavelocalai.runs.hub import RunHub

router = APIRouter(prefix="/api")


class EvalBody(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=MAX_QUESTIONS)
    models: list[str]  # 1 à 4 modèles distincts : vérifié par le service, qui résout les tags
    judge: str | None = None
    allow_cloud: bool = False

    @field_validator("questions")
    @classmethod
    def _each_question(cls, values: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > MAX_QUESTION_CHARS for v in values):
            raise ValueError(
                f"chaque question est non vide, de {MAX_QUESTION_CHARS} caractères au plus"
            )
        return values


class EvalStarted(BaseModel):
    run_id: str


def build_service(
    app: FastAPI, hub: RunHub, factory: ModelFactory, index: VectorIndex, guard: Guard | None
) -> EvaluationService:
    """Le service d'évaluation câblé à la base (`rag/eval_base.py`) et au juge de l'Arène."""
    state = app.state
    settings = state.settings
    return EvaluationService(
        hub,
        state.registry,
        factory,
        state.local_slot,
        settings,
        EvalRetrieval(
            hub,
            state.registry,
            factory,
            state.local_slot,
            settings,
            index,
            meter=state.meter,
            bus=state.system_feed,
            preferences=state.preferences,
        ),
        Judge(
            hub, state.local_slot, settings, meter=state.meter, bus=state.system_feed, guard=guard
        ),
        meter=state.meter,
        bus=state.system_feed,
        guard=guard,
        defaults=state.defaults,
    )


@router.post("/rag/eval/runs")
async def start_eval_run(body: EvalBody, request: Request) -> EvalStarted:
    service: EvaluationService | None = request.app.state.evaluation
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service d'évaluation n'est pas démarré.")
    handle = await service.start(EvalCommand(**body.model_dump()))
    return EvalStarted(run_id=handle.run_id)


@router.get("/rag/eval/runs")
async def eval_runs(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> dict[str, Any]:
    store = request.app.state.store
    if store is None:  # hors du cycle de vie : rien à lister
        return {"runs": []}
    return {"runs": await list_eval_runs(store, limit)}


@router.delete("/rag/eval/runs/{run_id}", status_code=204)
async def delete_eval_run(run_id: str, request: Request) -> Response:
    hub: RunHub | None = request.app.state.hub
    if hub is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le hub des runs n'est pas démarré.")
    await hub.erase_eval(run_id)
    return Response(status_code=204)
