"""`POST /api/test/runs` : lance un run scripté du modèle `fake` (AD-8).

Enregistrée seulement si `Settings.testing` est vrai (variable `WAVELOCALAI_TESTING`). Elle sert
aux tests E2E des composants du front avant le premier écran qui génère. Le script est une liste
d'étapes, chacune un objet à une clé principale :

- `{"text": "…", "channel": "answer" | "thought"}` : un morceau de texte ;
- `{"sleep_s": 0.2}` : une pause (au plus 30 s) ;
- `{"load": "loading" | "loaded", "duration_s": 0.1}` : l'état de chargement ;
- `{"fail": "<code d'errors.py>", "technical": "…"}` : une `ProviderError` ;
- `{"done": {…champs de ChatResult…}}` : le résultat final (sinon le `fake` en émet un).

`origin` (`local` ou `cloud`) et `co2` (champ `co2` d'AD-10) fixent la mesure de la feuille ; une fois
le run terminé, la route publie `carbon_updated` comme le feront les services (AD-10).
"""

from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from wavelocalai.errors import AppError, ProviderError
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.streaming import NOT_MEASURED, stream_into_run
from wavelocalai.models.fake import FakeChatModel, Sleep, Step
from wavelocalai.models.port import (
    ChatMessage,
    ChatRequest,
    ChatResult,
    Done,
    LoadState,
    TextDelta,
)
from wavelocalai.runs.models import CONVERSATION_KINDS, ROOT_KINDS, Co2, RunHandle

router = APIRouter(prefix="/api/test")

MAX_SLEEP_S = 30.0
DEFAULT_SCRIPT: list[dict[str, Any]] = [{"text": "Bonjour"}, {"text": " le monde"}]


class ScriptedRun(BaseModel):
    kind: str = "chat"
    model: str = "fake:1b"
    message: str | None = None  # ouvre une conversation (genres chat, rag, agent)
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
        body.kind, models=[body.model], params={"scripted": True}, user_message=body.message
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
