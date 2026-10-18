"""Service minimal d'un run « une génération » : il lit le flux d'un `ChatModel` et le publie dans le
hub (AD-5, AD-6, AD-8).

C'est le patron que suivent les services de chat, de RAG et d'agent : le service crée le run, lance
`stream_into_run` dans une tâche qu'il attache au hub (`attach_task`), et ne fixe jamais le statut
lui-même. L'annulation est celle de la tâche : le flux de l'adaptateur est fermé dans le `finally`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterable
from contextlib import AbstractAsyncContextManager, nullcontext

from wavelocalai.errors import ERRORS, AppError, ProviderError, build_envelope
from wavelocalai.models.port import (
    ChatChunk,
    ChatModel,
    ChatRequest,
    ChatResult,
    Done,
    LoadState,
    TextDelta,
)
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import Co2, LeafResult

logger = logging.getLogger("wavelocalai.inference")

# Tant que `greenops/` n'existe pas (étape 4), une génération n'a pas de mesure de CO2.
NOT_MEASURED = Co2(mg=None, method="unmeasurable", reason="mesure non branchée")


def _metrics(lane: str, result: ChatResult, origin: str, co2: Co2) -> dict[str, object]:
    return {
        "lane": lane,
        "ttft_s": result.ttft_s,
        "load_s": result.load_s,
        "eval_tokens": result.output_tokens,
        "eval_s": result.eval_s,
        "tps": result.tps,
        "tps_source": result.tps_source,
        "total_s": result.total_s,
        "co2": co2.as_dict(),
        "origin": origin,
    }


async def _attempt(
    hub: RunHub,
    run_id: str,
    model: ChatModel,
    request: ChatRequest,
    slot: AbstractAsyncContextManager[object] | None,
    timeout_s: float | None,
) -> ChatResult:
    """Un appel de modèle : place du sémaphore « Ollama local » prise pour cet appel seulement
    (AD-14), puis flux publié dans le hub sous le délai de lane. Le délai court depuis la prise de
    la place (local) ou le départ de l'appel (cloud, sans place). Le flux de l'adaptateur est
    fermé dans le `finally`, annulation comprise."""
    lane = model.ref.tag
    gate = slot if slot is not None and model.ref.origin == "local" else nullcontext()
    async with gate:
        deadline = asyncio.timeout(timeout_s)
        try:
            async with deadline:
                return await _consume(hub, run_id, lane, model.stream(request))
        except TimeoutError:
            if not deadline.expired():
                raise
            raise ProviderError(
                "timeout", f"Aucune fin de réponse après {timeout_s} s.", timeout_s=timeout_s
            ) from None


async def _consume(
    hub: RunHub, run_id: str, lane: str, stream: AsyncIterator[ChatChunk]
) -> ChatResult:
    result = ChatResult()
    try:
        async for chunk in stream:
            if isinstance(chunk, TextDelta):
                hub.publish_token(run_id, lane, chunk.text, chunk.channel)
            elif isinstance(chunk, LoadState):
                kind = "model_loading" if chunk.phase == "loading" else "model_loaded"
                hub.publish(run_id, kind, {"tag": lane, "duration_s": chunk.duration_s})
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
    slot: AbstractAsyncContextManager[object] | None = None,
    timeout_s: float | None = None,
    retry_interrupted: bool = False,
) -> None:
    """Joue une génération sur le run racine `run_id` (une feuille racine) jusqu'à sa fin.

    Termine par `hub.finish_leaf` : `ok` avec les métriques de `Done`, `error` avec l'enveloppe
    d'AD-18 si l'adaptateur lève une `ProviderError` (ou toute `AppError`) ; une annulation laisse
    le hub fixer `cancelled` et garder le partiel. Les appels d'outils (`ToolCall`) attendent la
    story des agents.

    `slot` : sémaphore local, pris par appel. `timeout_s` : délai de lane de chaque appel (`timeout`
    en cas de dépassement). `retry_interrupted` : une génération coupée (`generation_interrupted`)
    est relancée une fois, avec un événement `retry` qui efface le texte partiel ; copie adaptée de
    `retry_interrupted` de la v1 : toute autre erreur, délai compris, est relayée sans relance.
    """
    lane = model.ref.tag
    origin = model.ref.origin
    attempts = 2 if retry_interrupted else 1
    result = ChatResult()
    for attempt in range(1, attempts + 1):
        try:
            result = await _attempt(hub, run_id, model, request, slot, timeout_s)
            break
        except asyncio.CancelledError:
            raise  # `hub.cancel` a déjà fixé `cancelled` ; le `finally` d'`_consume` a fermé le flux
        except Exception as exc:
            if (
                attempt < attempts
                and isinstance(exc, ProviderError)
                and exc.code == "generation_interrupted"
            ):
                logger.warning("Génération de %s interrompue : relance unique.", lane)
                hub.publish(
                    run_id,
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
            await hub.finish_leaf(
                run_id, LeafResult(status="error", origin=origin, error=error), co2
            )
            return
    hub.publish(run_id, "metrics", _metrics(lane, result, origin, co2))
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
    )
    await hub.finish_leaf(run_id, leaf, co2)


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
