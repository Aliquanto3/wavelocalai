"""Service minimal d'un run « une génération » : il lit le flux d'un `ChatModel` et le publie dans le
hub (AD-5, AD-6, AD-8).

C'est le patron que suivent les services de chat, de RAG et d'agent : le service crée le run, lance
`stream_into_run` dans une tâche qu'il attache au hub (`attach_task`), et ne fixe jamais le statut
lui-même. L'annulation est celle de la tâche : le flux de l'adaptateur est fermé dans le `finally`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext

from wavelocalai.errors import ERRORS, AppError, ProviderError, build_envelope
from wavelocalai.greenops.local_meter import Footprint, LocalMeter, combine
from wavelocalai.models.port import (
    ChatChunk,
    ChatModel,
    ChatRequest,
    ChatResult,
    Done,
    LoadState,
    ModelRef,
    TextDelta,
)
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, LeafResult

logger = logging.getLogger("wavelocalai.inference")

# Sans compteur (feuille cloud avant ecologits, service sans `LocalMeter`), pas de mesure de CO2.
NOT_MEASURED = Co2(mg=None, method="unmeasurable", reason="mesure non branchée")
# Feuille annulée (ou arrêtée) avant sa fin : son `co2` reste présent, sans valeur (AD-10).
CANCELLED_CO2 = Co2(mg=None, method="unmeasurable", reason="réponse annulée avant la fin")
# Une feuille locale en erreur ne retient pas de mesure : l'énergie d'un appel raté n'est pas celle
# d'une réponse, et un inconnu n'est jamais un 0 (AD-10).
FAILED_CO2 = Co2(mg=None, method="unmeasurable", reason="réponse en erreur : aucune mesure retenue")
# Garde-fou mémoire : le modèle n'a jamais chargé, rien n'a été mesuré (story 4.8).
NOT_LOADED_CO2 = Co2(
    mg=None, method="unmeasurable", reason="modèle non chargé : mémoire insuffisante"
)


def _metrics(
    lane: str, result: ChatResult, origin: str, co2: Co2, footprint: Footprint | None = None
) -> dict[str, object]:
    return {
        "lane": lane,
        "ttft_s": result.ttft_s,
        "load_s": result.load_s,
        "eval_tokens": result.output_tokens,
        "eval_s": result.eval_s,
        "tps": result.tps,
        "tps_source": result.tps_source,
        "total_s": result.total_s,
        "prefill_s": result.prefill_s,  # ajout à `contrat-api.md` (story 2.1), à ratifier
        "prefill_tps": result.prefill_tps,
        "co2": co2.as_dict(),
        "energy_wh": None if footprint is None else footprint.energy_wh,
        "origin": origin,
    }


PhaseCallback = Callable[[str], None]  # "loading" | "generating" (Arène : `lane_status`)
# Garde-fou d'un appel local (story 4.8) : lève `ram_guard` si le modèle ne tient pas en mémoire.
Guard = Callable[[ModelRef], Awaitable[None]]


async def _attempt(
    hub: RunHub,
    run_id: str,
    model: ChatModel,
    request: ChatRequest,
    slot: AbstractAsyncContextManager[object] | None,
    timeout_s: float | None,
    on_phase: PhaseCallback | None = None,
    meter: LocalMeter | None = None,
    footprints: list[Footprint] | None = None,
    guard: Guard | None = None,
    capture: list[str] | None = None,
) -> ChatResult:
    """Un appel de modèle : place du sémaphore « Ollama local » prise pour cet appel seulement
    (AD-14), puis flux publié dans le hub sous le délai de lane. Le délai court depuis la prise de
    la place (local) ou le départ de l'appel (cloud, sans place). Le flux de l'adaptateur est
    fermé dans le `finally`, annulation comprise.

    Un appel local est mesuré par `meter` **dans la place** (AD-11) : le tracker démarre après la
    prise et s'arrête avant la remise, hors du délai de lane (son démarrage peut durer quelques
    secondes). La mesure est ajoutée à `footprints`, que l'appel réussisse ou non.

    `guard` (appel local seulement) s'exécute **dans la place**, avant le tracker et avant tout
    événement de phase : un refus (`ram_guard`) ne lance ni mesure ni chargement."""
    lane = model.ref.tag
    local = model.ref.origin == "local"
    gate = slot if slot is not None and local else nullcontext()
    async with gate:
        if guard is not None and local:
            await guard(model.ref)
        async with _tracking(meter if local else None, footprints):
            if on_phase is not None:
                on_phase("generating")  # place prise et tracker démarré (local), ou appel cloud
            deadline = asyncio.timeout(timeout_s)
            try:
                async with deadline:
                    return await _consume(
                        hub, run_id, lane, model.stream(request), on_phase, capture
                    )
            except TimeoutError:
                if not deadline.expired():
                    raise
                raise ProviderError(
                    "timeout", f"Aucune fin de réponse après {timeout_s} s.", timeout_s=timeout_s
                ) from None


@asynccontextmanager
async def _tracking(
    meter: LocalMeter | None, footprints: list[Footprint] | None
) -> AsyncIterator[None]:
    """Un tracker autour du bloc ; sa mesure rejoint `footprints` à la sortie, annulation et
    erreur comprises (`meter.track` ne lève pas)."""
    if meter is None:
        yield
        return
    tracking = None
    try:
        async with meter.track() as tracking:
            yield
    finally:
        if footprints is not None and tracking is not None and tracking.footprint is not None:
            footprints.append(tracking.footprint)


async def _consume(
    hub: RunHub,
    run_id: str,
    lane: str,
    stream: AsyncIterator[ChatChunk],
    on_phase: PhaseCallback | None = None,
    capture: list[str] | None = None,
) -> ChatResult:
    result = ChatResult()
    try:
        async for chunk in stream:
            if capture is not None:  # appel silencieux : le texte est gardé, rien n'est publié
                if isinstance(chunk, TextDelta) and chunk.channel == "answer":
                    capture.append(chunk.text)
                elif isinstance(chunk, Done):
                    result = chunk.result
            elif isinstance(chunk, TextDelta):
                hub.publish_token(run_id, lane, chunk.text, chunk.channel)
            elif isinstance(chunk, LoadState):
                kind = "model_loading" if chunk.phase == "loading" else "model_loaded"
                hub.publish(run_id, kind, {"tag": lane, "duration_s": chunk.duration_s})
                if on_phase is not None:
                    on_phase("loading" if chunk.phase == "loading" else "generating")
            elif isinstance(chunk, Done):
                result = chunk.result
    finally:
        aclose = getattr(stream, "aclose", None)
        if aclose is not None:
            await aclose()
    return result


async def stream_into_run(
    hub: RunHub,
    run_id: str,
    model: ChatModel,
    request: ChatRequest,
    *,
    secrets: Iterable[str] = (),
    co2: Co2 = NOT_MEASURED,
    estimate_co2: Callable[[ChatResult], Co2] | None = None,
    slot: AbstractAsyncContextManager[object] | None = None,
    timeout_s: float | None = None,
    retry_interrupted: bool = False,
    publish_to: str | None = None,
    on_phase: PhaseCallback | None = None,
    meter: LocalMeter | None = None,
    on_leaf_closed: Callable[[], Awaitable[None]] | None = None,
    capture: list[str] | None = None,
    metrics_extra: Mapping[str, object] | None = None,
    guard: Guard | None = None,
    publish_metrics: bool = False,
) -> LeafResult:
    """Joue une génération sur le run `run_id` jusqu'à sa fin ; rend le `LeafResult` passé à
    `hub.finish_leaf` (statut `ok` ou `error`, l'erreur d'AD-18).

    Run racine sans enfants (chat) : `run_id` publie son propre flux. Feuille d'un run composite
    (Arène) : `publish_to` est le parent, seul à publier (AD-5), et `run_id` la feuille que le hub
    termine avec ses métriques et son `co2` ; `on_phase` reçoit `generating` à la prise de la place
    (ou au départ de l'appel cloud), `loading` pendant le chargement du modèle.

    Termine par `hub.finish_leaf` : `ok` avec les métriques de `Done`, `error` avec l'enveloppe
    d'AD-18 si l'adaptateur lève une `ProviderError` (ou toute `AppError`) ; une annulation laisse
    le hub fixer `cancelled` et garder le partiel. Les appels d'outils (`ToolCall`) attendent la
    story des agents.

    `slot` : sémaphore local, pris par appel. `timeout_s` : délai de lane de chaque appel (`timeout`
    en cas de dépassement). `estimate_co2` : calcule le `co2` d'une réponse cloud réussie à partir
    de son `ChatResult` (ecologits), hors de la boucle d'événements ; il ne lève jamais.
    `retry_interrupted` : une génération coupée (`generation_interrupted`)
    est relancée une fois, avec un événement `retry` qui efface le texte partiel ; copie adaptée de
    `retry_interrupted` de la v1 : toute autre erreur, délai compris, est relayée sans relance.

    `meter` : compteur CodeCarbon d'une feuille locale (story 2.3) ; sans lui, ou pour une feuille
    cloud, le `co2` est celui passé en argument. `on_leaf_closed` est attendu quand la feuille est
    close, annulation comprise (le hub a alors déjà clos le run) : le service y publie
    `carbon_updated`. Son échec est journalisé, il n'interrompt rien.

    `capture` : appel **silencieux** (une notation, story 3.3). Le texte de réponse est ajouté à
    cette liste (vidée à chaque tentative) et rien n'est publié dans le flux du parent : ni jetons,
    ni chargement, ni `metrics`, ni `retry`. La feuille reste mesurée et close comme les autres.

    `metrics_extra` : champs ajoutés à l'événement `metrics` de la feuille (le RAG y met la durée de
    la recherche, `retrieval_s`) ; ils ne remplacent jamais un champ du flux.

    `guard` : garde-fou mémoire d'un appel local (story 4.8), appelé dans la place avant le modèle ;
    son `ram_guard` met la feuille en `error` avec son enveloppe, sans relance ni mesure.

    `publish_metrics` : avec `capture`, publie quand même l'événement `metrics` de la feuille (une
    réponse évaluée, story 7.1 : texte gardé à part, débit et CO2 dans le flux, sans jetons).
    """
    try:
        return await _play(
            hub,
            run_id,
            publish_to or run_id,
            model,
            request,
            secrets,
            co2,
            estimate_co2,
            slot,
            timeout_s,
            retry_interrupted,
            meter,
            on_phase,
            capture=capture,
            metrics_extra=metrics_extra,
            guard=guard,
            publish_metrics=publish_metrics,
        )
    finally:
        if on_leaf_closed is not None:
            try:
                await on_leaf_closed()
            except Exception:  # noqa: BLE001 - aucune mesure n'interrompt un run
                logger.exception("Publication de carbon_updated en échec")


async def _play(
    hub: RunHub,
    run_id: str,
    stream_id: str,
    model: ChatModel,
    request: ChatRequest,
    secrets: Iterable[str],
    co2: Co2,
    estimate_co2: Callable[[ChatResult], Co2] | None,
    slot: AbstractAsyncContextManager[object] | None,
    timeout_s: float | None,
    retry_interrupted: bool,
    meter: LocalMeter | None,
    on_phase: PhaseCallback | None,
    capture: list[str] | None = None,
    metrics_extra: Mapping[str, object] | None = None,
    guard: Guard | None = None,
    publish_metrics: bool = False,
) -> LeafResult:
    lane = model.ref.tag
    origin = model.ref.origin
    hub.declare_leaf(run_id, CANCELLED_CO2)
    attempts = 2 if retry_interrupted else 1
    result = ChatResult()
    footprints: list[Footprint] = []
    for attempt in range(1, attempts + 1):
        if capture is not None:
            capture.clear()
        try:
            result = await _attempt(
                hub,
                stream_id,
                model,
                request,
                slot,
                timeout_s,
                on_phase,
                meter,
                footprints,
                guard=guard,
                capture=capture,
            )
            break
        except asyncio.CancelledError:
            # `hub.cancel` a déjà fixé `cancelled` ; le `finally` d'`_consume` a fermé le flux. Le
            # tracker est arrêté : l'énergie dépensée jusqu'à l'arrêt remplace le `co2` de remplacement.
            await _amend_cancelled(hub, run_id, footprints)
            raise
        except Exception as exc:
            if (
                attempt < attempts
                and isinstance(exc, ProviderError)
                and exc.code == "generation_interrupted"
            ):
                logger.warning("Génération de %s interrompue : relance unique.", lane)
                if capture is None:
                    hub.publish(
                        stream_id,
                        "retry",
                        {
                            "lane": lane,
                            "code": exc.code,
                            "reason": ERRORS[exc.code].message,
                            "attempt": attempt + 1,
                        },
                    )
                continue
            error = _error_envelope(exc, secrets)
            # Le `co2` est présent partout (AD-10) : une feuille en erreur reste non mesurée.
            failed = LeafResult(status="error", origin=origin, error=error)
            refused = isinstance(exc, AppError) and exc.code == "ram_guard"
            await hub.finish_leaf(
                run_id, failed, NOT_LOADED_CO2 if refused else FAILED_CO2 if footprints else co2
            )
            return failed
    footprint = combine(footprints)
    if footprint is not None:
        co2 = footprint.co2()
    elif estimate_co2 is not None:  # cloud : estimé après l'appel, sur les jetons et la durée réels
        try:
            co2 = await asyncio.to_thread(estimate_co2, result)
        except Exception as exc:  # noqa: BLE001 - aucune mesure n'interrompt un run (AD-11)
            logger.warning("Estimation du CO2 impossible : %r", exc)
            co2 = Co2(mg=None, method="unmeasurable", reason="l'estimation a échoué")
    if capture is None or publish_metrics:
        metrics = _metrics(lane, result, origin, co2, footprint)
        metrics.update({k: v for k, v in (metrics_extra or {}).items() if k not in metrics})
        hub.publish(stream_id, "metrics", metrics)
    leaf = LeafResult(
        origin=origin,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        ttft_s=result.ttft_s,
        load_s=result.load_s,
        eval_s=result.eval_s,
        total_s=result.total_s,
        tps=result.tps,
        tps_source=result.tps_source,
        energy_wh=None if footprint is None else footprint.energy_wh,
    )
    await hub.finish_leaf(run_id, leaf, co2)
    return leaf


async def _amend_cancelled(hub: RunHub, run_id: str, footprints: list[Footprint]) -> None:
    footprint = combine(footprints)
    if footprint is None or not footprint.measured:
        return
    try:
        await hub.amend_cancelled_leaf(run_id, footprint.co2(), footprint.energy_wh)
    except Exception:  # noqa: BLE001 - aucune mesure n'interrompt un run
        logger.exception("Mesure d'une feuille annulée non écrite")


def _error_envelope(exc: Exception, secrets: Iterable[str]) -> dict[str, object]:
    """Enveloppe d'AD-18 pour `run_ended.data.error` ; une exception inattendue devient `internal`."""
    if isinstance(exc, AppError):
        # Clés de `detail` non déclarées pour ce code : écartées plutôt que de lever ici, ce qui
        # laisserait le run actif (et sa place de `kind` prise) jusqu'au redémarrage.
        declared = ERRORS[exc.code].detail_keys
        dropped = sorted(set(exc.detail) - set(declared))
        if dropped:
            logger.warning("Clés de detail non déclarées pour %s écartées : %s", exc.code, dropped)
        detail = {key: value for key, value in exc.detail.items() if key in declared}
        return build_envelope(exc.code, exc.technical, secrets, **detail)
    logger.error("Erreur non prévue dans un run", exc_info=exc)
    return build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
