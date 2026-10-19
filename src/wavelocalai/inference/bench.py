"""Banc d'essai : un scénario prédéfini, un modèle, et le verdict de format (story 7.4, AD-3, AD-5).

Le service crée le run `bench` (une génération, racine et feuille à la fois, comme le chat), publie
`bench_input` (le texte saisi vit dans le flux, jamais dans `runs.params`, AD-7), puis lit le flux
du modèle avec `stream_into_run`. Quand le scénario attend un format, le serveur dit lui-même si la
sortie le respecte (AD-20) : `format_verdict` est ajouté à l'événement `metrics`, qui précède
`run_ended`, et l'instantané le relit (`runs/bench_snapshot.py`).

`force_format` passe le schéma à l'adaptateur (`response_schema`, AD-8 : `format` d'Ollama). Un
adaptateur qui trouve la sortie non conforme lève `invalid_output` en fin de flux ; le Banc ne
l'affiche pas comme une panne mais comme un format violé : `_Tee` garde alors le texte déjà reçu,
termine le flux sans compte de jetons, et le verdict dit la première violation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from wavelocalai.config import Settings
from wavelocalai.errors import AppError, ProviderError, build_envelope
from wavelocalai.greenops.local_meter import LocalMeter
from wavelocalai.greenops.session import announce_carbon_updated
from wavelocalai.inference.chat import cloud_estimator
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.scenarios import CONCISE_INSTRUCTION, Scenario, find_scenario
from wavelocalai.inference.streaming import CANCELLED_CO2, NOT_MEASURED, Guard, stream_into_run
from wavelocalai.models.factory import ModelFactory
from wavelocalai.models.port import (
    ChatChunk,
    ChatMessage,
    ChatModel,
    ChatRequest,
    ChatResult,
    Done,
    ModelRef,
    TextDelta,
)
from wavelocalai.models.registry import ModelRegistry
from wavelocalai.models.structured import schema_errors, strip_fence
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import LeafResult, RunHandle
from wavelocalai.runs.system_bus import SystemBus

logger = logging.getLogger("wavelocalai.inference")

MAX_INPUT_CHARS = 20_000
TEMPERATURE = 0.2  # celle de la v1 (curseur par défaut du Banc)
NBSP = " "
RESPECTED = "Format respecté"
_TYPES_FR = {
    "object": "objet",
    "array": "tableau",
    "string": "texte",
    "integer": "entier",
    "number": "nombre",
    "boolean": "booléen",
    "null": "nul",
}
_TYPE_EXPECTED = "type attendu "
_FENCE_LINE = re.compile(r"^```", re.MULTILINE)  # une ligne qui ouvre ou ferme un bloc Markdown


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} n'est pas une valeur JSON")


def _where(path: str) -> str:
    """`$.a.b` devient « a.b » ; la racine (`$`) devient « la réponse »."""
    rest = path.removeprefix("$").removeprefix(".")
    return f"« {rest} »" if rest else "la réponse"


def _plain(error: str) -> str:
    """Une violation de `schema_errors` en clair : champ entre guillemets, types en français."""
    path, _, reason = error.partition(" : ")
    wanted = reason.removeprefix(_TYPE_EXPECTED)
    if wanted != reason:  # seuls les noms de type sont traduits, jamais les valeurs permises
        reason = _TYPE_EXPECTED + "/".join(_TYPES_FR.get(name, name) for name in wanted.split("/"))
    where = _where(path)
    return f"{where[0].upper()}{where[1:]}{NBSP}: {reason}"


def format_verdict(text: str, schema: dict[str, Any], *, forced: bool = False) -> dict[str, Any]:
    """La sortie respecte-t-elle le schéma ? `{ok, message, formatted, forced}` : `message` est
    « Format respecté » ou la **première** violation en clair ; `formatted` est le JSON mis en forme
    (lu même s'il viole le schéma), `None` s'il n'est pas lisible. Une clôture Markdown autour du
    JSON est tolérée, comme par les adaptateurs."""
    body = strip_fence(text)
    try:
        value = json.loads(body, parse_constant=_reject_constant)  # NaN, Infinity : pas du JSON
    except ValueError as exc:
        return {"ok": False, "message": _unreadable(body, exc), "formatted": None, "forced": forced}
    errors = schema_errors(value, schema)
    return {
        "ok": not errors,
        "message": RESPECTED if not errors else _plain(errors[0]),
        "formatted": json.dumps(value, ensure_ascii=False, indent=2),
        "forced": forced,
    }


def _unreadable(body: str, exc: ValueError) -> str:
    """Pourquoi la sortie n'est pas lisible, en clair : vide, texte autour d'un bloc Markdown, texte
    après le JSON, ou position de la première erreur."""
    if not body:
        return "La sortie est vide"
    if _FENCE_LINE.search(body):
        return "La sortie a du texte autour de son bloc JSON"
    if not isinstance(exc, json.JSONDecodeError):
        return "La sortie n'est pas du JSON valide (NaN ou Infinity)"
    where = f"ligne {exc.lineno}, colonne {exc.colno}"
    if exc.msg == "Extra data":
        return f"La sortie a du texte après son JSON ({where})"
    return f"La sortie n'est pas du JSON valide ({where})"


class _Tee:
    """Modèle enveloppé : garde le texte de réponse de la tentative en cours (le verdict le lit) et
    transforme `invalid_output` (format imposé violé) en fin de flux ordinaire."""

    def __init__(self, inner: ChatModel) -> None:
        self._inner = inner
        self.ref: ModelRef = inner.ref
        self.parts: list[str] = []

    @property
    def text(self) -> str:
        return "".join(self.parts)

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        self.parts = []  # une tentative relancée repart de zéro
        started = time.monotonic()
        try:
            async for chunk in self._inner.stream(request):
                if isinstance(chunk, TextDelta) and chunk.channel == "answer":
                    self.parts.append(chunk.text)
                yield chunk
        except ProviderError as exc:
            if exc.code != "invalid_output":
                raise
            yield Done(ChatResult(total_s=round(time.monotonic() - started, 3)))


@dataclass(frozen=True)
class BenchCommand:
    scenario: str
    model: str
    input: str
    force_format: bool = False
    concise: bool = False
    allow_cloud: bool = False


class BenchService:
    def __init__(
        self,
        hub: RunHub,
        registry: ModelRegistry,
        factory: ModelFactory,
        slot: LocalSlot,
        settings: Settings,
        meter: LocalMeter | None = None,
        bus: SystemBus | None = None,
        guard: Guard | None = None,
    ) -> None:
        self._hub = hub
        self._registry = registry
        self._factory = factory
        self._slot = slot
        self._settings = settings
        self._meter = meter
        self._bus = bus
        self._guard = guard
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self, command: BenchCommand) -> RunHandle:
        """Crée le run et rend `{run_id}` aussitôt. Lève `invalid_request` (scénario inconnu, entrée
        vide ou trop longue, format imposé à un scénario sans format), `model_not_found`,
        `cloud_not_allowed` ou `model_not_chat` (registre), `run_busy` (un banc est actif)."""
        scenario = find_scenario(command.scenario)
        if scenario is None:
            raise AppError("invalid_request", f"Scénario inconnu : {command.scenario}.")
        if not command.input.strip() or len(command.input) > MAX_INPUT_CHARS:
            raise AppError(
                "invalid_request",
                f"L'entrée est vide ou dépasse {MAX_INPUT_CHARS} caractères.",
            )
        if command.force_format and scenario.schema is None:
            raise AppError(
                "invalid_request", f"Le scénario « {scenario.name} » n'a pas de format à imposer."
            )
        ref = self._registry.resolve(command.model, command.allow_cloud)
        model = _Tee(self._factory.chat_model(ref))
        handle = await self._hub.create_run(
            "bench",
            models=[ref.tag],
            params={
                "scenario": scenario.id,
                "force_format": command.force_format,
                "concise": command.concise,
                "allow_cloud": command.allow_cloud,
            },
        )
        self._hub.publish(
            handle.run_id, "bench_input", {"scenario": scenario.id, "text": command.input}
        )
        self._hub.declare_leaf(handle.run_id, CANCELLED_CO2)
        task = asyncio.create_task(
            self._run(handle, model, scenario, command), name=f"wavelocalai-bench-{handle.run_id}"
        )
        self._hub.attach_task(handle.run_id, task)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return handle

    async def _run(
        self, handle: RunHandle, model: _Tee, scenario: Scenario, command: BenchCommand
    ) -> None:
        secrets = self._settings.secret_values()
        instruction = scenario.instruction
        if command.concise:
            instruction = f"{instruction}\n\n{CONCISE_INSTRUCTION}"
        schema = scenario.schema
        request = ChatRequest(
            messages=[ChatMessage("system", instruction), ChatMessage("user", command.input)],
            temperature=TEMPERATURE,
            response_schema=schema if command.force_format else None,
        )

        def verdict(_: Any) -> dict[str, Any]:
            if schema is None:
                return {}
            return {
                "format_verdict": format_verdict(model.text, schema, forced=command.force_format)
            }

        try:
            await stream_into_run(
                self._hub,
                handle.run_id,
                model,
                request,
                secrets=secrets,
                estimate_co2=cloud_estimator(model, self._settings),
                slot=self._slot,
                timeout_s=self._settings.delays.lane_timeout_s,
                retry_interrupted=True,
                meter=self._meter,
                on_leaf_closed=self._announce_carbon,
                guard=self._guard,
                metrics_extra=verdict,
            )
        except Exception as exc:  # noqa: BLE001 - ne jamais laisser le run actif
            logger.error("Banc d'essai en échec", exc_info=exc)
            error = build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
            await self._hub.finish_leaf(
                handle.run_id,
                LeafResult(status="error", origin=model.ref.origin, error=error),
                NOT_MEASURED,
            )

    async def _announce_carbon(self) -> None:
        session_id = self._hub.app_session_id
        if self._bus is None or session_id is None:
            return
        try:
            await announce_carbon_updated(self._bus, self._hub.store, session_id)
        except Exception as exc:  # noqa: BLE001 - une annonce manquée ne change pas le run
            logger.warning("carbon_updated non publié : %r", exc)
