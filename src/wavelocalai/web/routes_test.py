"""`POST /api/test/runs` : lance un run scripté du modèle `fake` (AD-8).

Enregistrée seulement si `Settings.testing` est vrai (variable `WAVELOCALAI_TESTING`). Elle sert
aux tests E2E des composants du front avant le premier écran qui génère. Le script est une liste
d'étapes, chacune un objet à une clé principale :

- `{"text": "…", "channel": "answer" | "thought"}` : un morceau de texte ;
- `{"sleep_s": 0.2}` : une pause (au plus 30 s) ;
- `{"load": "loading" | "loaded", "duration_s": 0.1}` : l'état de chargement ;
- `{"fail": "<code d'errors.py>", "technical": "…"}` : une `ProviderError` ;
- `{"done": {…champs de ChatResult…}}` : le résultat final (sinon le `fake` en émet un).

`POST /api/test/embedder` règle le `FakeEmbedder` de la même façon (story 4.2).

`conversation_id` prolonge une conversation. `origin` (`local` ou `cloud`) et `co2` (champ `co2`
d'AD-10) fixent la mesure de la feuille ; une fois le run terminé, la route publie
`carbon_updated` comme le feront les services (AD-10).

`POST /api/test/arena` lance une Arène dont chaque lane est un `fake` scripté (`tag`, `origin`,
`script` comme ci-dessus), par le vrai service de l'Arène : sémaphore, délais, flux du parent.
`judge` (`tag`, `origin`, `script`) ajoute un juge `fake` au vrai service de notation : son script
rend le JSON `{"score": …, "reason": …}` (ou échoue) ; sans `judge`, aucune notation n'est câblée.
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from wavelocalai.errors import AppError, ProviderError
from wavelocalai.evaluation.judge import Judge
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.arena import ArenaCommand, ArenaService
from wavelocalai.inference.streaming import NOT_MEASURED, stream_into_run
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.fake import FakeChatModel, FakeEmbedder, Sleep, Step
from wavelocalai.models.port import (
    ChatMessage,
    ChatRequest,
    ChatResult,
    Done,
    LoadState,
    ModelRef,
    TextDelta,
)
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.runs.models import CONVERSATION_KINDS, ROOT_KINDS, Co2, RunHandle

router = APIRouter(prefix="/api/test")

MAX_SLEEP_S = 30.0
DEFAULT_SCRIPT: list[dict[str, Any]] = [{"text": "Bonjour"}, {"text": " le monde"}]


class ScriptedRun(BaseModel):
    kind: str = "chat"
    model: str = "fake:1b"
    message: str | None = None  # ouvre une conversation (genres chat, rag, agent)
    conversation_id: str | None = None  # ou prolonge celle-ci (avec `message`)
    script: list[dict[str, Any]] = Field(default_factory=lambda: list(DEFAULT_SCRIPT))
    origin: Literal["local", "cloud"] | None = None
    co2: dict[str, Any] | None = None


class Started(BaseModel):
    run_id: str
    conversation_id: str | None


def parse_script(items: list[dict[str, Any]]) -> list[Step]:
    steps: list[Step] = []
    for index, item in enumerate(items):
        try:
            if "text" in item:
                steps.append(TextDelta(str(item["text"]), item.get("channel", "answer")))
            elif "sleep_s" in item:
                steps.append(Sleep(min(float(item["sleep_s"]), MAX_SLEEP_S)))
            elif "load" in item:
                steps.append(LoadState(item["load"], item.get("duration_s")))
            elif "fail" in item:
                steps.append(ProviderError(item["fail"], item.get("technical")))
            elif "done" in item:
                steps.append(Done(ChatResult(**item["done"])))
            else:
                raise ValueError("étape inconnue")
        except (ValueError, TypeError) as exc:
            raise AppError("invalid_request", f"script[{index}] : {exc}") from None
    return steps


@router.post("/runs")
async def start_scripted_run(body: ScriptedRun, request: Request) -> Started:
    state = request.app.state
    model = state.models.get(body.model)
    if not isinstance(model, FakeChatModel):
        raise AppError("not_found", f"Modèle factice {body.model!r} inconnu.")
    if body.kind not in ROOT_KINDS:
        raise AppError("invalid_request", f"kind doit être parmi {ROOT_KINDS}.")
    if body.message is not None and body.kind not in CONVERSATION_KINDS:
        raise AppError("invalid_request", f"Un run {body.kind} n'ouvre pas de conversation.")
    ref = model.ref if body.origin is None else dataclasses.replace(model.ref, origin=body.origin)
    scripted = FakeChatModel(parse_script(body.script), ref)
    try:
        co2 = NOT_MEASURED if body.co2 is None else Co2(**body.co2)
    except (ValueError, TypeError) as exc:
        raise AppError("invalid_request", f"co2 : {exc}") from None
    hub = state.hub
    handle: RunHandle = await hub.create_run(
        body.kind,
        models=[body.model],
        params={"scripted": True},
        user_message=body.message,
        conversation_id=body.conversation_id,
    )
    chat = ChatRequest([ChatMessage("user", body.message or "")])

    async def play() -> None:
        await stream_into_run(
            hub, handle.run_id, scripted, chat, secrets=state.settings.secret_values(), co2=co2
        )
        if hub.app_session_id is not None:
            await announce_carbon_updated(state.system_feed, state.store, hub.app_session_id)

    task = asyncio.create_task(play(), name=f"wavelocalai-test-run-{handle.run_id}")
    hub.attach_task(handle.run_id, task)
    state.tasks.add(task)  # référence forte jusqu'à la fin
    task.add_done_callback(state.tasks.discard)
    return Started(run_id=handle.run_id, conversation_id=handle.conversation_id)


class ScriptedEmbedder(BaseModel):
    script: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/embedder")
async def script_embedder(body: ScriptedEmbedder, request: Request) -> dict[str, int]:
    """Script du `FakeEmbedder` : une étape par lot d'embedding, dans l'ordre, à partir du
    prochain import (`{"sleep_s": 0.3}` ou `{"fail": "<code>"}`). Un script vide le rend instantané.
    """
    steps = parse_script(body.script)
    if not all(isinstance(step, Sleep | ProviderError) for step in steps):
        raise AppError("invalid_request", "script : seuls sleep_s et fail valent pour un embedder.")
    for embedder in request.app.state.embedders.values():
        if isinstance(embedder, FakeEmbedder):
            embedder.script = list(steps)
            embedder.calls = 0
    return {"steps": len(steps)}


class ScriptedLane(BaseModel):
    tag: str
    origin: Literal["local", "cloud"] = "local"
    script: list[dict[str, Any]] = Field(default_factory=lambda: list(DEFAULT_SCRIPT))


class ScriptedArena(BaseModel):
    lanes: list[ScriptedLane]
    prompt: str
    criteria: list[str] = Field(default_factory=list)
    allow_cloud: bool = True
    judge: ScriptedLane | None = None  # le juge `fake` (son `tag` est celui de la commande)


class ArenaStarted(BaseModel):
    run_id: str


@router.post("/arena")
async def start_scripted_arena(body: ScriptedArena, request: Request) -> ArenaStarted:
    """Une Arène dont chaque lane est un `fake` scripté, par le vrai service (hub, sémaphore, délais).

    Les modèles de la requête ne vivent que dans un registre et une fabrique à part, sans compteur
    CodeCarbon (le CO2 des lanes locales n'est pas mesuré) : l'application n'enregistre rien."""
    state = request.app.state
    fakes: dict[str, FakeChatModel] = {}
    for lane in body.lanes:
        ref = ModelRef(lane.tag, "fake", lane.origin, "chat")
        fakes[lane.tag] = FakeChatModel(parse_script(lane.script), ref)
    scorer = None
    if body.judge is not None:
        ref = ModelRef(body.judge.tag, "fake", body.judge.origin, "chat")
        fakes[body.judge.tag] = FakeChatModel(parse_script(body.judge.script), ref)
        scorer = Judge(state.hub, state.local_slot, state.settings, bus=state.system_feed)
    service = ArenaService(
        state.hub,
        ModelRegistry(state.settings, extra_refs={tag: model.ref for tag, model in fakes.items()}),
        ModelFactory(state.ollama_client, fakes, state.settings),
        state.local_slot,
        state.settings,
        bus=state.system_feed,
        judge=scorer,
    )
    handle = await service.start(
        ArenaCommand(
            models=[lane.tag for lane in body.lanes],
            prompt=body.prompt,
            judge=body.judge.tag if body.judge else None,
            criteria=body.criteria,
            allow_cloud=body.allow_cloud,
        )
    )
    return ArenaStarted(run_id=handle.run_id)
