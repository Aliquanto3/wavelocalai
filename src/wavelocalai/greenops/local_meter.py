"""Mesure CO2 d'une feuille locale par CodeCarbon (AD-10, AD-11, AD-14).

Copie adaptée de `LocalMeter` de `wavestack/greenops.py` (jamais importée, AD-2). Un
`OfflineEmissionsTracker` par appel de modèle local, démarré et arrêté **sous le sémaphore Ollama**
(le service ouvre `meter.track()` dans la place de `LocalSlot`), un seul à la fois (un verrou
propre au compteur le garantit même hors du sémaphore), `start` et `stop` dans le pool de threads
(CodeCarbon interroge le matériel, parfois pendant plusieurs secondes sous Windows). Le pays et le
PUE viennent de `Settings`. Aucun réseau : le tracker `Offline` reçoit le pays, rien n'est écrit
sur disque (`save_to_file=False`), ni envoyé (`save_to_api=False`).

Aucune mesure n'interrompt un run : un échec de CodeCarbon (absent, démarrage, arrêt, énergie
illisible) donne un `co2` `unmeasurable` avec sa raison, jamais un 0.

`codecarbon` n'est importé que dans `load_tracker_class` (AD-4, AD-21).
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import math
import warnings
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from wavelocalai.config import CarbonSettings
from wavelocalai.runs.models import Co2

logger = logging.getLogger("wavelocalai.greenops")

# CodeCarbon donne l'énergie en kWh et les émissions en kg de CO2e.
WH_PER_KWH = 1000.0
MG_PER_KG = 1_000_000.0
MEASURE_INTERVAL_S = 1.0


def load_tracker_class() -> Any:
    """`OfflineEmissionsTracker`, importé ici seulement (remplacé par un double dans les tests).

    Le journal de CodeCarbon est ramené à l'erreur ; sous Windows il interroge PowerShell pour
    compter les sockets du processeur à chaque tracker (~2 s) : une fois suffit."""
    import codecarbon.emissions_tracker as module

    logging.getLogger("codecarbon").setLevel(logging.ERROR)
    counter = getattr(module, "count_physical_cpus", None)
    if counter is not None and not hasattr(counter, "cache_info"):
        module.count_physical_cpus = functools.cache(counter)
    return module.OfflineEmissionsTracker


@dataclass(frozen=True)
class Footprint:
    """Ce qu'a mesuré un tracker : émissions en mg et énergie en Wh, ou la raison de son échec."""

    mg: float | None = None
    energy_wh: float | None = None
    reason: str | None = None

    @property
    def measured(self) -> bool:
        return self.mg is not None

    def co2(self) -> Co2:
        if self.mg is None:
            return Co2(mg=None, method="unmeasurable", reason=self.reason or "mesure indisponible")
        return Co2(
            mg=self.mg,
            method="codecarbon",
            estimated=False,
            range_mg=None,
            allocation="direct",
            reason=None,
        )


def combine(footprints: Sequence[Footprint]) -> Footprint | None:
    """Somme des appels d'une même feuille (une relance en compte deux). Un seul appel non
    mesuré rend la somme inconnue : elle sous-estimerait, et un inconnu n'est jamais un 0.
    `None` si aucun appel n'a été mesuré (feuille cloud, ou fin avant tout appel)."""
    if not footprints:
        return None
    unmeasured = next((f for f in footprints if not f.measured), None)
    if unmeasured is not None:
        return unmeasured
    return Footprint(
        mg=sum(f.mg or 0.0 for f in footprints),
        energy_wh=sum(f.energy_wh or 0.0 for f in footprints),
    )


class Tracking:
    """Le résultat d'un `meter.track()`, lisible une fois le bloc fermé."""

    def __init__(self) -> None:
        self.footprint: Footprint | None = None


@dataclass
class _Started:
    tracker: Any  # None si le démarrage a échoué
    reason: str | None = None


class LocalMeter:
    """CodeCarbon autour de chaque appel local ; une instance par serveur."""

    def __init__(
        self,
        country_iso_code: str,
        pue: float,
        loader: Callable[[], Any] | None = None,
    ) -> None:
        self.country_iso_code = country_iso_code
        self.pue = pue
        self._loader = loader or load_tracker_class
        self._lock = asyncio.Lock()  # un seul tracker à la fois, de `start` à `stop`

    @classmethod
    def from_settings(cls, carbon: CarbonSettings) -> LocalMeter:
        return cls(carbon.country_iso, carbon.pue)

    @contextlib.asynccontextmanager
    async def track(self) -> AsyncIterator[Tracking]:
        """Démarre un tracker, rend la main le temps de l'appel, puis l'arrête. Ne lève jamais :
        `tracking.footprint` dit la mesure, ou pourquoi elle manque. Annulation comprise, le
        tracker est arrêté avant de rendre la main."""
        tracking = Tracking()
        async with self._lock:
            started = await self._start()
            try:
                yield tracking
            finally:
                tracking.footprint = await asyncio.shield(self._stop(started))

    # --- fils ----------------------------------------------------------------------------------

    async def _start(self) -> _Started:
        task = asyncio.ensure_future(asyncio.to_thread(self._start_sync))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            # Le fil démarre (ou a démarré) un tracker : on l'arrête avant de laisser partir.
            with contextlib.suppress(Exception):
                await asyncio.shield(self._stop(await task))
            raise

    async def _stop(self, started: _Started) -> Footprint:
        return await asyncio.to_thread(self._stop_sync, started)

    def _start_sync(self) -> _Started:
        try:
            tracker_class = self._loader()
        except Exception as exc:  # noqa: BLE001 - une mesure n'arrête jamais un run
            logger.warning("CodeCarbon est indisponible : %s", exc)
            return _Started(None, f"CodeCarbon est indisponible ({type(exc).__name__}).")
        try:
            with warnings.catch_warnings():  # `save_to_file`, déprécié par CodeCarbon 3
                warnings.simplefilter("ignore", DeprecationWarning)
                tracker = tracker_class(
                    country_iso_code=self.country_iso_code,
                    pue=self.pue,
                    save_to_file=False,
                    save_to_api=False,
                    log_level="error",
                    measure_power_secs=MEASURE_INTERVAL_S,
                    tracking_mode="machine",  # Ollama est un autre processus
                    allow_multiple_runs=True,  # un seul à la fois, par notre verrou, sans fichier
                )
            tracker.start()
        except Exception as exc:  # noqa: BLE001
            logger.warning("CodeCarbon n'a pas démarré : %s", exc)
            return _Started(None, f"CodeCarbon n'a pas démarré ({type(exc).__name__}).")
        if getattr(tracker, "_another_instance_already_running", False):
            return _Started(None, "CodeCarbon n'a pas démarré (un autre compteur est actif).")
        return _Started(tracker)

    @staticmethod
    def _stop_sync(started: _Started) -> Footprint:
        if started.tracker is None:
            return Footprint(reason=started.reason)
        try:
            started.tracker.stop()  # CodeCarbon avale ses erreurs : on lit ce qu'il a gardé
            data = started.tracker.final_emissions_data
            kwh = float(data.energy_consumed)
            kg = float(data.emissions)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CodeCarbon a échoué : %s", exc)
            return Footprint(reason=f"CodeCarbon n'a rien mesuré ({type(exc).__name__}).")
        if not (math.isfinite(kwh) and math.isfinite(kg)) or kwh <= 0 or kg <= 0:
            return Footprint(reason="CodeCarbon a rendu une énergie nulle ou illisible.")
        return Footprint(mg=kg * MG_PER_KG, energy_wh=kwh * WH_PER_KWH)
