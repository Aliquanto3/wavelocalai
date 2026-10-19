"""Un appel d'embedding = une feuille `embedding` mesurée (AD-5, AD-10, AD-11, AD-14).

Partagé par l'ingestion (un lot d'extraits) et la question (le texte posé) : la place du
`LocalSlot` est prise par appel, le tracker CodeCarbon tourne dedans, l'appel est sous le délai de
lane, et la feuille est close avec ses métriques et son `co2` (annulation et erreur comprises). Le
service crée la feuille (`hub.create_run("embedding", parent_run_id=...)`) et la déclare
(`hub.declare_leaf`) ; ce module la termine.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from wavelocalai.errors import ERRORS, AppError, ProviderError, build_envelope
from wavelocalai.greenops.local_meter import Footprint, LocalMeter, combine
from wavelocalai.inference.local_slot import LocalSlot
from wavelocalai.inference.streaming import FAILED_CO2, NOT_MEASURED
from wavelocalai.models.port import Embedder
from wavelocalai.runs.hub import RunHub
from wavelocalai.runs.models import LeafResult

logger = logging.getLogger("wavelocalai.rag")


async def embed_into_leaf(
    hub: RunHub,
    leaf_id: str,
    embedder: Embedder,
    texts: list[str],
    *,
    slot: LocalSlot,
    meter: LocalMeter | None,
    timeout_s: float,
    secrets: Sequence[str],
    on_leaf_closed: Callable[[], Awaitable[None]] | None = None,
) -> list[list[float]]:
    """Vectorise `texts` dans la feuille `leaf_id` et la termine ; rend les vecteurs.

    Une erreur ferme la feuille en `error` (`co2` non mesuré, jamais 0) puis est relayée ;
    une annulation écrit l'énergie dépensée jusqu'à l'arrêt (le hub a déjà clos la feuille).
    `on_leaf_closed` est attendu après `finish_leaf` (réussi ou en erreur) : le service y publie
    `carbon_updated`."""
    footprints: list[Footprint] = []
    started = time.perf_counter()
    try:
        # La place est prise par appel, pas par run (AD-14) ; le tracker tourne dedans (AD-11).
        async with slot, _tracking(meter, footprints):
            try:
                async with asyncio.timeout(timeout_s) as deadline:
                    vectors = await embedder.embed(texts)
            except TimeoutError:
                if not deadline.expired():
                    raise
                raise ProviderError(
                    "timeout", f"Aucun embedding après {timeout_s} s.", timeout_s=timeout_s
                ) from None
    except asyncio.CancelledError:
        await _amend_cancelled(hub, leaf_id, footprints)
        raise
    except Exception as exc:
        await hub.finish_leaf(
            leaf_id,
            LeafResult(status="error", origin="local", error=leaf_error(exc, secrets)),
            FAILED_CO2 if footprints else NOT_MEASURED,
        )
        await _closed(on_leaf_closed)
        raise
    footprint = combine(footprints)
    await hub.finish_leaf(
        leaf_id,
        LeafResult(
            origin="local",
            total_s=round(time.perf_counter() - started, 6),
            energy_wh=None if footprint is None else footprint.energy_wh,
        ),
        NOT_MEASURED if footprint is None else footprint.co2(),
    )
    await _closed(on_leaf_closed)
    return vectors


async def _closed(callback: Callable[[], Awaitable[None]] | None) -> None:
    if callback is not None:
        await callback()


@contextlib.asynccontextmanager
async def _tracking(meter: LocalMeter | None, footprints: list[Footprint]) -> AsyncIterator[None]:
    """Un tracker CodeCarbon autour du bloc, dans la place du `LocalSlot` ; sa mesure rejoint
    `footprints` à la sortie, annulation et erreur comprises (`meter.track` ne lève pas)."""
    if meter is None:
        yield
        return
    tracking = None
    try:
        async with meter.track() as tracking:
            yield
    finally:
        if tracking is not None and tracking.footprint is not None:
            footprints.append(tracking.footprint)


async def _amend_cancelled(hub: RunHub, leaf_id: str, footprints: list[Footprint]) -> None:
    """Le hub a clos la feuille annulée avec le `co2` de remplacement : l'énergie dépensée jusqu'à
    l'arrêt le remplace (AD-10)."""
    footprint = combine(footprints)
    if footprint is None or not footprint.measured:
        return
    try:
        await hub.amend_cancelled_leaf(leaf_id, footprint.co2(), footprint.energy_wh)
    except Exception:  # noqa: BLE001 - aucune mesure n'interrompt un run
        logger.exception("Mesure d'une feuille annulée non écrite")


def leaf_error(exc: Exception, secrets: Sequence[str]) -> dict[str, object]:
    """Enveloppe d'AD-18 d'une feuille en erreur ; une exception inattendue devient `internal`."""
    if isinstance(exc, AppError):
        declared = ERRORS[exc.code].detail_keys
        detail = {key: value for key, value in exc.detail.items() if key in declared}
        return build_envelope(exc.code, exc.technical, secrets, **detail)
    return build_envelope("internal", f"{type(exc).__name__}: {exc}", secrets)
