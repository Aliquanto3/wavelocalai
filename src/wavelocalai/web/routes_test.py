"""`POST /api/test/runs` : lance un run scripté du modèle `fake` (AD-8).

Enregistrée seulement si `Settings.testing` est vrai (variable `WAVELOCALAI_TESTING`). Elle sert
aux tests E2E des composants du front avant le premier écran qui génère. Le script est une liste
d'étapes, chacune un objet à une clé principale :

- `{"text": "…", "channel": "answer" | "thought"}` : un morceau de texte ;
- `{"sleep_s": 0.2}` : une pause (au plus 30 s) ;
- `{"load": "loading" | "loaded", "duration_s": 0.1}` : l'état de chargement ;
- `{"fail": "<code d'errors.py>", "technical": "…", "detail": {…}}` : une `ProviderError`, avec
  les clés machine déclarées avec son code (`ram_guard` : `needed_gb`, `free_gb`, …) ;
- `{"done": {…champs de ChatResult…}}` : le résultat final (sinon le `fake` en émet un) ;
- `{"tool_call": {"id": "…", "name": "…", "arguments": {…}}}` : un appel d'outil du modèle (agents,
  story 6.4) ; un script par appel de modèle se donne par `scripts` (`POST /api/test/chat-model`).

`POST /api/test/embedder` règle le `FakeEmbedder` de la même façon (story 4.2).
`POST /api/test/chat-model` fixe le script du `fake` pour les prochaines commandes réelles
(`POST /api/rag/runs`, `POST /api/chat/runs`), jusqu'au prochain appel (story 4.5).
`POST /api/test/reranker` remplace le reranker de l'app par un `FakeReranker` (`lexical` ou
`reverse`, `delay_s`), ou le déclare indisponible (`absent`, avec sa `reason`) ; `GET` rend les
calculs qu'il a faits (story 4.7).
`POST /api/test/reranker-install` remplace l'installation du reranker (écran Modèles, story 5.5) par une
installation factice (`ok`, `fail`, `hang`, octets simulés) et règle la présence de l'extra « rerank » ;
une fois installé, le reranker chargé est un `FakeReranker` : aucun réseau, aucun modèle.
`POST /api/test/gpu` fixe l'état du GPU que le flux système publie (`gpu` : nom, mémoire, température,
bridage thermique ; `null` : aucun GPU, le champ est absent), au lieu de la lecture NVML du poste (5.1).
`POST /api/test/carbon-sessions` ajoute des sessions closes, datées dans le passé, à l'historique
carbone (`days_ago`, feuilles `kind`, `origin`, `mg` ou nul ; story 5.2).

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
import shutil
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
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
    ToolCall,
)
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.rag.rerank import FakeReranker, install_marker
from wavelocalai.rag.rerank_pull import FakeFetcher, RerankerPullService, model_folder
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
                steps.append(
                    ProviderError(item["fail"], item.get("technical"), **(item.get("detail") or {}))
                )
            elif "done" in item:
                steps.append(Done(ChatResult(**item["done"])))
            elif "tool_call" in item:
                call = item["tool_call"]
                steps.append(ToolCall(str(call["id"]), str(call["name"]), dict(call["arguments"])))
            else:
                raise ValueError("étape inconnue")
        except (ValueError, TypeError, KeyError) as exc:
            raise AppError("invalid_request", f"script[{index}] : {exc!r}") from None
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


class ScriptedGpu(BaseModel):
    gpu: dict[str, Any] | None = None


@router.post("/gpu")
async def script_gpu(body: ScriptedGpu, request: Request) -> dict[str, bool]:
    """État du GPU publié par le flux système : celui du corps (ou aucun), à la place de NVML.
    Les valeurs sont celles de `GpuState` ; une clé manquante est une erreur de test."""
    state = body.gpu
    if state is not None:
        missing = {
            "name",
            "memory_used_gb",
            "memory_total_gb",
            "temperature_c",
            "thermal_throttle",
        } - set(state)
        if missing:
            raise AppError("invalid_request", f"gpu : champs manquants {sorted(missing)}.")
        state = {"throttle_reasons": [], **state}
    request.app.state.system_sampler.gpu_reader = lambda: state
    return {"gpu": state is not None}


class SeededLeaf(BaseModel):
    kind: Literal["chat", "rag", "agent"] = "chat"
    origin: Literal["local", "cloud"] = "local"
    mg: float | None = None  # nul : réponse non mesurable


class SeededSession(BaseModel):
    days_ago: float = Field(ge=0)
    leaves: list[SeededLeaf] = Field(default_factory=list)


class SeededSessions(BaseModel):
    sessions: list[SeededSession]


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@router.post("/carbon-sessions")
async def seed_carbon_sessions(body: SeededSessions, request: Request) -> dict[str, int]:
    """Sessions closes du passé, avec leurs feuilles terminées, pour l'historique carbone : la CI ne
    peut pas attendre sept jours. Chaque session dure cinq minutes ; la session courante n'est pas
    touchée."""
    now = datetime.now(UTC)

    def write(conn: sqlite3.Connection) -> int:
        count = 0
        for session in body.sessions:
            started = now - timedelta(days=session.days_ago)
            session_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO app_sessions (id, started_at, reason) VALUES (?, ?, 'startup')",
                (session_id, _iso(started)),
            )
            for index, leaf in enumerate(session.leaves):
                measured = leaf.mg is not None
                conn.execute(
                    "INSERT INTO runs (id, kind, app_session, model, status, started_at, ended_at,"
                    " origin, co2_mg, co2_method, co2_estimated, co2_reason, params)"
                    " VALUES (?, ?, ?, 'fake:1b', 'ok', ?, ?, ?, ?, ?, ?, ?, '{}')",
                    (
                        uuid.uuid4().hex,
                        leaf.kind,
                        session_id,
                        _iso(started + timedelta(seconds=index)),
                        _iso(started + timedelta(minutes=5)),
                        leaf.origin,
                        leaf.mg,
                        (
                            ("ecologits" if leaf.origin == "cloud" else "codecarbon")
                            if measured
                            else "unmeasurable"
                        ),
                        int(leaf.origin == "cloud") if measured else 0,
                        None if measured else "essai",
                    ),
                )
            count += 1
        return count

    return {"sessions": await request.app.state.store.awrite(write)}


class ScriptedChatModel(BaseModel):
    model: str = "fake:1b"
    script: list[dict[str, Any]] = Field(default_factory=lambda: list(DEFAULT_SCRIPT))
    # Un script par appel, dans l'ordre (le dernier se répète) : HyDE et Self-RAG appellent le
    # modèle plusieurs fois par question (story 4.6). Sans lui, `script` sert à chaque appel.
    scripts: list[list[dict[str, Any]]] = Field(default_factory=list)


@router.post("/chat-model")
async def script_chat_model(body: ScriptedChatModel, request: Request) -> dict[str, int]:
    """Script du `fake` que les commandes réelles interrogent (une réponse scriptée sans passer par
    `/api/test/runs`, qui contourne la route testée)."""
    model = request.app.state.models.get(body.model)
    if not isinstance(model, FakeChatModel):
        raise AppError("not_found", f"Modèle factice {body.model!r} inconnu.")
    model.script = parse_script(body.script)
    model.scripts = [parse_script(script) for script in body.scripts]
    model.opened = 0  # les scripts par appel repartent du premier
    return {"steps": len(model.script)}


class ScriptedReranker(BaseModel):
    mode: Literal["lexical", "reverse", "absent"] = "lexical"
    delay_s: float = Field(default=0.0, ge=0.0, le=MAX_SLEEP_S)
    reason: str = "le modèle de test n'est pas dans le cache"  # pour `absent`


@router.post("/reranker")
async def script_reranker(body: ScriptedReranker, request: Request) -> dict[str, Any]:
    """Un reranker factice pour les prochaines questions (aucun modèle, aucun réseau)."""
    service = request.app.state.reranker
    if body.mode == "absent":
        service.preset(None, body.reason)
    else:
        service.preset(FakeReranker(body.mode, body.delay_s))
    return {"available": service.status().available}


class ScriptedRerankerInstall(BaseModel):
    extra: bool = True  # l'extra « rerank » est présent
    mode: Literal["ok", "fail", "hang"] = "ok"
    total_bytes: int = Field(default=1_000_000_000, ge=0)
    steps: int = Field(default=4, ge=1, le=100)
    step_delay_s: float = Field(default=0.0, ge=0.0, le=MAX_SLEEP_S)
    interval_s: float = Field(default=0.05, gt=0.0, le=MAX_SLEEP_S)  # entre deux `pull_progress`
    reason: str = "connexion refusée"


@router.post("/reranker-install")
async def script_reranker_install(
    body: ScriptedRerankerInstall, request: Request
) -> dict[str, Any]:
    """Une installation du reranker factice : l'état du reranker repart de zéro (extra réglé, cache vide)."""
    app = request.app
    service = app.state.reranker
    fake = FakeFetcher(
        body.mode,
        total_bytes=body.total_bytes,
        steps=body.steps,
        step_delay_s=body.step_delay_s,
        reason=body.reason,
    )
    service.extra_override = body.extra
    service.use_loader(lambda model, cache, env_file: FakeReranker())
    service.refresh()
    shutil.rmtree(model_folder(service.cache, service.model), ignore_errors=True)
    install_marker(service.cache, service.model).unlink(missing_ok=True)
    app.state.reranker_pull = RerankerPullService(
        app.state.hub,
        service,
        app.state.settings,
        fetch=fake.fetch,
        expected=fake.expected,
        measure=fake.measure,
        interval_s=body.interval_s,
    )
    app.state.reranker_fetcher = fake
    return {"available": service.status().available}


@router.get("/reranker-install")
async def reranker_install_calls(request: Request) -> dict[str, int]:
    """Le nombre de téléchargements factices lancés (zéro : aucun n'a été tenté)."""
    fake = getattr(request.app.state, "reranker_fetcher", None)
    return {"downloads": fake.calls if fake is not None else 0}


@router.get("/reranker")
async def reranker_calls(request: Request) -> dict[str, Any]:
    """Les calculs du `FakeReranker` : `(question, nombre de textes)` de chacun, dans l'ordre."""
    reranker = request.app.state.reranker.loaded
    calls = reranker.calls if isinstance(reranker, FakeReranker) else []
    return {"calls": [{"question": question, "texts": count} for question, count in calls]}


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
