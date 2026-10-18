"""Registre des modèles : liste unique locale et cloud, et seul accès à un modèle (AD-9, AD-15).

La liste se reconstruit en mémoire (ce n'est pas une table) depuis :
- Ollama (`/api/tags`, puis `/api/show` mis en cache par `(tag, digest)` dans `model_facts`) ;
- `Settings` pour le cloud (clé présente = fournisseur configuré, listes fixes du `.toml`) ;
- le catalogue versionné `config/models_catalog.json`, en lecture seule ;
- le débit mesuré sur ce poste (`RunStats`) et la mémoire du poste (`MemoryAdvisor`, injecté par
  `web/` : `models/` n'importe pas `hardware/`, AD-4).

Aucune route de lecture n'attend Ollama : `list_models` sert la dernière liste connue et lance un
rafraîchissement en tâche de fond quand le cache a plus de `cache_s`. Seul le tout premier appel
attend `wait_s` au plus. Aucun SDK cloud n'est appelé.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel

from wavelocalai.config import Settings
from wavelocalai.errors import AppError
from wavelocalai.models.catalog import Catalog, CatalogEntry, load_catalog
from wavelocalai.models.classify import (
    base_tag,
    is_dedicated_reasoning,
    is_embedding_model,
    is_remote_tag,
    is_reranker_model,
)
from wavelocalai.models.facts import FactsStore, InMemoryFactsStore, ModelFacts, facts_from_ollama
from wavelocalai.models.ollama_api import OllamaHttpSource, OllamaSource, OllamaUnavailableError
from wavelocalai.models.port import Kind, ModelRef, Origin
from wavelocalai.models.run_stats import InMemoryRunStats, RunStats
from wavelocalai.store.db import utc_now_iso

logger = logging.getLogger("wavelocalai.models")

CO2Method = Literal["codecarbon", "ecologits", "unmeasurable"]
# Fournisseurs que ecologits couvre en direct (AD-11) ; Groq passe par la table du `.toml`.
ECOLOGITS_DIRECT = frozenset({"openai", "anthropic", "mistral"})
SHOW_CONCURRENCY = 4
BYTES_PER_GB = 1024**3


class FitLike(Protocol):
    needed_gb: float | None
    fits: bool | None


class MemoryAdvisorLike(Protocol):
    """Fourni par `hardware/` (`MemoryAdvisor`) : `models/` ne l'importe pas."""

    def assess(
        self,
        *,
        measured_loaded_gb: float | None = None,
        download_gb: float | None = None,
        download_bytes: int | None = None,
    ) -> FitLike: ...


class ModelInfo(BaseModel):
    tag: str
    name: str
    provider: str
    editor: str | None = None
    origin: Origin
    kind: Kind
    available: bool  # local : Ollama répond ; cloud : clé présente
    digest: str | None = None
    params_total_b: float | None = None
    params_active_b: float | None = None  # MoE : `null` si inconnu, jamais le total par défaut
    size_gb: float | None = None
    quantization: str | None = None
    context_length: int | None = None
    needed_gb: float | None = None  # mémoire nécessaire (hardware/) ; `null` si inconnue
    fits: bool | None = None  # `null` : taille inconnue ou modèle non local
    tools_verified: bool = False
    reasoning: bool = False
    throughput_tps: float | None = None  # médiane mesurée sur ce poste ; `null` sans run
    accuracy: float | None = None  # `qb.results/1` dès l'étape 5 ; `null` avant
    co2_method: CO2Method
    in_catalog: bool = False


class ModelList(BaseModel):
    models: list[ModelInfo]
    ollama_up: bool
    refreshed_at: str | None  # dernier rafraîchissement réussi (ISO 8601 UTC) ; `null` jamais


@dataclass(frozen=True)
class _Local:
    facts: ModelFacts
    remote: bool


def _classify(facts: ModelFacts) -> Kind:
    if is_reranker_model(facts.tag):
        return "reranker"
    caps = set(facts.capabilities)
    if is_embedding_model({"model": facts.tag, "details": {"family": facts.family}}) or (
        "embedding" in caps and "completion" not in caps
    ):
        return "embedding"
    return "chat"


def _is_moe(facts: ModelFacts, entry: CatalogEntry | None) -> bool:
    """MoE d'après les experts de `/api/show`, le catalogue ou la famille (`lfm2moe`) : ce dernier
    indice reste disponible quand `/api/show` ne l'est pas."""
    return bool(
        facts.expert_count or (entry and entry.moe) or "moe" in (facts.family or "").lower()
    )


def _origin(rec: _Local) -> Origin:
    if rec.remote:
        return "cloud"
    return "local" if rec.facts.digest else "unknown"


class ModelRegistry:
    def __init__(
        self,
        settings: Settings,
        *,
        source: OllamaSource | None = None,
        facts: FactsStore | None = None,
        run_stats: RunStats | None = None,
        advisor: MemoryAdvisorLike | None = None,
        catalog_path: Path | None = None,
        cache_s: float | None = None,
        wait_s: float = 0.1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._source = source or OllamaHttpSource(
            settings.ollama.host, timeout_s=settings.ollama.probe_timeout_s
        )
        self._facts = facts or InMemoryFactsStore()
        self._run_stats = run_stats or InMemoryRunStats()
        self._advisor = advisor
        self._catalog_path = catalog_path or settings.base_dir / "config" / "models_catalog.json"
        self._catalog: Catalog | None = None
        self._cache_s = settings.ollama.probe_cache_s if cache_s is None else cache_s
        self._wait_s = wait_s
        self._clock = clock
        self._local: dict[str, _Local] | None = None
        self._ollama_up = False
        self._attempted_at: float | None = None
        self._refreshed_at: str | None = None
        self._task: asyncio.Task[None] | None = None

    # -- rafraîchissement en tâche de fond ---------------------------------------------------

    async def refresh(self) -> None:
        """Relit Ollama (liste, puis détails des modèles au digest inconnu). Ne lève jamais :
        Ollama indisponible laisse la dernière liste connue."""
        try:
            listed = await self._source.list_tags()
        except OllamaUnavailableError:
            self._ollama_up = False
            self._attempted_at = self._clock()
            return
        gate = asyncio.Semaphore(SHOW_CONCURRENCY)

        async def one(item: dict) -> _Local | None:
            tag = str(item.get("model") or item.get("name") or "")
            if not tag:
                return None
            digest = str(item.get("digest") or "")
            cached = self._facts.get(tag, digest) if digest else None
            if cached is not None:
                return _Local(cached, is_remote_tag(item))
            show = None
            with contextlib.suppress(OllamaUnavailableError):
                async with gate:
                    show = await self._source.show(tag)
            facts = facts_from_ollama(item, show)
            if show is not None and digest:  # sans détails : pas de cache, on réessaiera
                self._facts.put(facts)
            return _Local(facts, is_remote_tag(item))

        try:
            records = await asyncio.gather(*(one(item) for item in listed))
        except Exception:  # noqa: BLE001 - un rafraîchissement ne doit jamais remonter
            logger.warning("Rafraîchissement des modèles interrompu", exc_info=True)
            self._attempted_at = self._clock()
            return
        self._local = {rec.facts.tag: rec for rec in records if rec is not None}
        self._ollama_up = True
        self._attempted_at = self._clock()
        self._refreshed_at = utc_now_iso()

    def invalidate(self) -> None:
        """Force le prochain `list_models` à relire Ollama (après un `pull` ou une suppression)."""
        self._attempted_at = None

    def _ensure_task(self) -> asyncio.Task[None]:
        loop = asyncio.get_running_loop()
        task = self._task
        if task is None or task.done() or task.get_loop() is not loop:
            task = self._task = loop.create_task(self.refresh())
        return task

    async def start(self) -> None:
        """Lance le premier rafraîchissement au démarrage du serveur, sans l'attendre."""
        self._ensure_task()

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    def _seed(self) -> dict[str, _Local]:
        """Dernière liste connue (`model_facts`) tant qu'Ollama n'a pas répondu."""
        if self._local is None:
            self._local = {
                facts.tag: _Local(facts, is_remote_tag({"model": facts.tag}))
                for facts in self._facts.latest_per_tag()
            }
        return self._local

    # -- lecture -------------------------------------------------------------------------------

    def _catalog_entry(self, tag: str) -> CatalogEntry | None:
        if self._catalog is None:
            self._catalog = load_catalog(self._catalog_path)
        return self._catalog.find(tag)

    async def list_models(self, *, allow_cloud: bool = False) -> ModelList:
        """Modèles disponibles ; ceux dont l'origine n'est pas `local` seulement si `allow_cloud`."""
        local = self._seed()
        first_call = self._attempted_at is None
        if first_call or self._clock() - (self._attempted_at or 0.0) >= self._cache_s:
            task = self._ensure_task()
            if first_call:  # tout premier appel : on laisse une chance à Ollama de répondre
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(asyncio.shield(task), self._wait_s)
                local = self._seed()
        medians = await asyncio.to_thread(self._run_stats.medians)  # lecture de `runs` hors boucle
        infos = [self._local_info(rec, medians) for rec in local.values()]
        infos += self._cloud_infos()
        if not allow_cloud:
            infos = [info for info in infos if info.origin == "local"]
        infos.sort(key=lambda info: (info.origin != "local", info.name.lower(), info.tag))
        return ModelList(models=infos, ollama_up=self._ollama_up, refreshed_at=self._refreshed_at)

    def _local_info(self, rec: _Local, medians: dict[str, float]) -> ModelInfo:
        facts = rec.facts
        origin = _origin(rec)
        entry = self._catalog_entry(facts.tag)
        kind = _classify(facts)
        caps = set(facts.capabilities)
        if entry is not None:
            caps_tools = "tools" in entry.capabilities
            caps_thinking = "thinking" in entry.capabilities
        else:
            caps_tools = "tools" in caps
            caps_thinking = "thinking" in caps
        total = facts.params_total_b or (entry.params_total_b if entry else None)
        if entry is not None and entry.params_active_b is not None:
            active = entry.params_active_b
        elif _is_moe(facts, entry):  # MoE sans valeur au catalogue : jamais le total
            active = None
        else:
            active = total
        needed = fits = None
        if origin == "local" and self._advisor is not None:
            assessment = self._advisor.assess(
                measured_loaded_gb=entry.measured_loaded_gb if entry else None,
                download_gb=entry.size_gb if entry else None,
                download_bytes=facts.size_bytes,
            )
            needed, fits = assessment.needed_gb, assessment.fits
        return ModelInfo(
            tag=facts.tag,
            name=entry.name if entry else facts.tag,
            provider="ollama",
            editor=entry.editor if entry else None,
            origin=origin,
            kind=kind,
            available=self._ollama_up,
            digest=facts.digest or None,
            params_total_b=_round(total),
            params_active_b=_round(active),
            size_gb=_round(facts.size_bytes / BYTES_PER_GB) if facts.size_bytes else None,
            quantization=facts.quantization,
            context_length=facts.context_length or (entry.context_length if entry else None),
            needed_gb=_round(needed),
            fits=fits,
            tools_verified=caps_tools,
            reasoning=caps_thinking
            or is_dedicated_reasoning(facts.tag, entry.name if entry else None),
            throughput_tps=medians.get(facts.tag),
            co2_method="codecarbon" if origin == "local" else "unmeasurable",
            in_catalog=entry is not None,
        )

    def _cloud_infos(self) -> list[ModelInfo]:
        infos: list[ModelInfo] = []
        for provider in self._settings.cloud.models:
            if not self._settings.api_keys.get(provider):
                continue
            for model in self._settings.cloud.models[provider]:
                infos.append(
                    ModelInfo(
                        tag=f"{provider}/{model}",
                        name=model,
                        provider=provider,
                        origin="cloud",
                        kind="chat",
                        available=True,
                        co2_method=self._cloud_co2_method(provider, model),
                    )
                )
        return infos

    def _cloud_co2_method(self, provider: str, model: str) -> CO2Method:
        if provider in ECOLOGITS_DIRECT:
            return "ecologits"
        if provider == "groq" and model in self._settings.cloud.groq_ecologits:
            return "ecologits"
        return "unmeasurable"

    # -- accès aux modèles (AD-9) ----------------------------------------------------------

    def _find(self, tag: str) -> ModelRef | None:
        local = self._seed()
        rec = local.get(tag)
        if rec is None:
            wanted = base_tag(tag)
            rec = next((r for t, r in local.items() if base_tag(t) == wanted), None)
        if rec is not None:
            return ModelRef(rec.facts.tag, "ollama", _origin(rec), _classify(rec.facts))
        provider, _, model = tag.partition("/")
        if (
            model
            and self._settings.api_keys.get(provider)
            and model in self._settings.cloud.models.get(provider, ())
        ):
            return ModelRef(tag, provider, "cloud", "chat")
        return None

    def resolve(self, tag: str, allow_cloud: bool = False) -> ModelRef:
        """Modèle de conversation pour générer. `allow_cloud` absent vaut faux : un modèle
        `origin != "local"` lève alors `cloud_not_allowed` (D1) ; un `kind != "chat"` lève
        `model_not_chat`."""
        ref = self._find(tag)
        if ref is None:
            raise AppError("model_not_found", f"Modèle inconnu : {tag}", tag=tag)
        if ref.origin != "local" and not allow_cloud:
            raise AppError("cloud_not_allowed", f"{tag} est hébergé hors de ce poste.", tag=ref.tag)
        if ref.kind != "chat":
            raise AppError(
                "model_not_chat", f"{tag} est de type {ref.kind}.", tag=ref.tag, kind=ref.kind
            )
        return ref

    def resolve_embedder(self, tag: str) -> ModelRef:
        """Modèle d'embedding : local seulement (AD-8), jamais d'envoi de texte vers le cloud."""
        ref = self._find(tag)
        if ref is None:
            raise AppError("model_not_found", f"Modèle inconnu : {tag}", tag=tag)
        if ref.origin != "local":
            raise AppError("cloud_not_allowed", f"{tag} est hébergé hors de ce poste.", tag=ref.tag)
        if ref.kind != "embedding":
            raise AppError(
                "model_not_embedding", f"{tag} est de type {ref.kind}.", tag=ref.tag, kind=ref.kind
            )
        return ref


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 3)
