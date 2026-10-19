"""Routes du Banc d'essai (story 7.4, AD-3, AD-5).

- `GET /api/scenarios` : les scénarios prédéfinis, avec leur consigne système (`instruction`, D-18)
  et leur format attendu en schéma JSON, ou `null` sans format (D-17).
- `POST /api/bench/runs {scenario, model, input, force_format, concise, allow_cloud}` : lance le run
  `bench` et rend `{run_id}` aussitôt. Le flux se lit par `GET /api/runs/{id}/events` (AD-6), le
  résultat, `bench` et `format_verdict` compris, par `GET /api/runs/{id}`.
- `GET /api/bench/runs?limit=` : les tests passés, les plus récents d'abord (décision n° 14).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from wavelocalai.errors import AppError
from wavelocalai.inference.bench import MAX_INPUT_CHARS, BenchCommand, BenchService
from wavelocalai.inference.scenarios import SCENARIOS
from wavelocalai.runs.bench_snapshot import list_bench_runs

router = APIRouter(prefix="/api")


class BenchBody(BaseModel):
    scenario: str = Field(min_length=1)
    model: str = Field(min_length=1)
    input: str = Field(max_length=MAX_INPUT_CHARS)
    force_format: bool = False
    concise: bool = False
    allow_cloud: bool = False


class BenchStarted(BaseModel):
    run_id: str


@router.get("/scenarios")
async def scenarios() -> dict[str, Any]:
    return {"scenarios": [scenario.as_dict() for scenario in SCENARIOS]}


@router.post("/bench/runs")
async def start_bench_run(body: BenchBody, request: Request) -> BenchStarted:
    service: BenchService | None = request.app.state.bench
    if service is None:  # hors du cycle de vie de l'app
        raise AppError("internal", "Le service du Banc d'essai n'est pas démarré.")
    handle = await service.start(BenchCommand(**body.model_dump()))
    return BenchStarted(run_id=handle.run_id)


@router.get("/bench/runs")
async def bench_runs(
    request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 20
) -> dict[str, Any]:
    store = request.app.state.store
    if store is None:  # hors du cycle de vie : rien à lister
        return {"runs": []}
    return {"runs": await list_bench_runs(store, limit)}
