"""Modèle par défaut de chaque usage, avec sa raison (AD-9, AD-15).

Règles de `src/core/model_defaults.py` (v1), copiées puis adaptées : elles portent sur les
`ModelInfo` du registre, qui a déjà fusionné le catalogue versionné, ce qu'Ollama dit, le débit
mesuré sur ce poste et la mémoire (`fits`) ; plus de `config`, de `models_db` ni de fichier lu
ici. Fonctions pures, sans réseau ni `streamlit`. Rien n'est importé de `src.*`.

Règle de choix, par usage :

- `chat` : modèles locaux d'abord (le cloud seulement s'il est autorisé et qu'aucun local n'est
  installé). Parmi les locaux, les modèles dédiés au raisonnement (« thinking » ou « reasoning »
  dans le tag ou le nom) passent après tous les autres ; puis ceux qui tiennent en mémoire, le
  plus rapide en tête. Le débit mesuré sur ce poste départage s'il existe pour tous les locaux
  qui tiennent, sinon la plus petite empreinte sert d'indicateur de vitesse. Ceux qui ne tiennent
  pas suivent, du plus petit au plus gros : si aucun ne tient, le plus petit est proposé.
- `judge` : cloud autorisé et modèles cloud proposés, le plus capable (`CLOUD_JUDGE_PREFERENCE`) ;
  sinon, quand la précision mesurée existe (`qb.results/1`, étape 5), le plus précis des locaux
  assez rapides ; sinon le plus gros local qui tient en mémoire (empreinte, puis paramètres
  actifs). Note peu fiable sous `JUDGE_MIN_PARAMS_B` paramètres actifs, ou s'ils sont inconnus.
- `arena` : les 2 ou 3 locaux les plus rapides qui tiennent, hors juge par défaut et hors modèles
  dédiés au raisonnement ; le juge n'y revient que s'il manque un modèle pour atteindre 2.
- `agent` : locaux qui tiennent, hors raisonnement, aux outils vérifiés et d'au moins
  `AGENT_MIN_PARAMS_B` paramètres actifs : le plus précis (si mesuré), puis le plus rapide. Sans
  candidat : aucun tag, et la raison le dit (comme la v1, qui ne proposait rien : un agent doit
  savoir appeler des outils).
- `rag` : comme `chat`, parmi les locaux hors raisonnement d'au moins `RAG_MIN_PARAMS_B`
  paramètres actifs qui tiennent ; sans candidat : le modèle de `chat`.

Un défaut n'est jamais un modèle d'embedding ni un reranker, ni un modèle cloud quand le cloud
n'est pas autorisé. Une préférence enregistrée par l'UI (`preferences`, clé
`default_model.<usage>`) prime sur la règle pour ce seul usage, à condition de viser des modèles
encore disponibles (locaux seulement et au moins 2 pour `arena`, un seul tag ailleurs).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, get_args

from pydantic import BaseModel

from wavelocalai.errors import AppError
from wavelocalai.models.classify import is_dedicated_reasoning
from wavelocalai.models.registry import ModelInfo, ModelList
from wavelocalai.store.preferences import PreferenceStore

Purpose = Literal["chat", "arena", "judge", "agent", "rag"]
PURPOSES: tuple[str, ...] = get_args(Purpose)
Source = Literal["rule", "preference"]

JUDGE_MIN_PARAMS_B = 4.0
AGENT_MIN_PARAMS_B = 3.0
RAG_MIN_PARAMS_B = 3.0
# Plancher de débit (tokens/s) pour juger d'après la précision mesurée.
BENCH_MIN_SPEED_TPS = 10.0
ARENA_MIN_MODELS = 2
ARENA_MAX_MODELS = 3
PREFERENCE_KEY = "default_model.{purpose}"

# Juges cloud, du plus capable au moins capable (préfixes du nom de modèle, sans le fournisseur).
# Opus 5.5 passe avant Fable 5.1 (environ 2,5 fois son prix) : le juge par défaut n'est pas le
# modèle le plus cher ; Fable reste sélectionnable.
CLOUD_JUDGE_PREFERENCE = (
    "claude-opus-5-5",
    "claude-fable-5-1",
    "gpt-6-sol",  # identifiants de `[cloud.models]` vérifiés le 2026-10-18 (story 2.4)
    "openai/gpt-oss-120b",  # Groq
    "mistral-large",
    "claude-sonnet-5-5",
    "claude-haiku-5-5",
    "gpt-6-luna",  # palier économique d'OpenAI
    "mistral-medium",
    "llama-3.3-70b-versatile",  # Groq
)
CLOUD_JUDGE_DEMOTED = ("gpt-4o-mini",)


def is_weak_judge(is_cloud: bool, params_active_b: float | None) -> bool:
    """Juge local de moins de ~4B paramètres actifs, ou de taille inconnue (« note peu fiable »)."""
    return not is_cloud and (params_active_b is None or params_active_b < JUDGE_MIN_PARAMS_B)


class ModelDefault(BaseModel):
    purpose: Purpose
    tags: list[str]  # un seul tag sauf `arena`
    reason: str  # en français, affichée en aide
    source: Source  # `rule` ou `preference` (choix de l'UI)


class ModelCatalogLike(Protocol):
    async def list_models(self, *, allow_cloud: bool = False) -> ModelList: ...


@dataclass(frozen=True)
class _Cand:
    """Ce que la règle sait d'un modèle de conversation proposé."""

    info: ModelInfo
    is_cloud: bool
    fits: bool
    footprint_gb: float
    reasoning: bool  # dédié au raisonnement (hybrides exclus)

    @property
    def tag(self) -> str:
        return self.info.tag

    @property
    def params_b(self) -> float | None:
        return self.info.params_active_b

    @property
    def speed(self) -> float | None:
        return self.info.throughput_tps

    @property
    def weak_judge(self) -> bool:
        """Juge local de moins de ~4B paramètres actifs, ou de taille inconnue."""
        return is_weak_judge(self.is_cloud, self.params_b)


def _candidates(models: Iterable[ModelInfo], allow_cloud: bool) -> list[_Cand]:
    """Modèles de conversation seulement (ni embedding ni reranker) ; hors cloud sans accord."""
    result = []
    for info in models:
        if info.kind != "chat":
            continue
        is_cloud = info.origin != "local"
        if is_cloud and not allow_cloud:
            continue
        footprint = info.needed_gb if info.needed_gb is not None else info.size_gb
        result.append(
            _Cand(
                info=info,
                is_cloud=is_cloud,
                fits=bool(info.fits) and not is_cloud,
                footprint_gb=footprint if footprint is not None else math.inf,
                reasoning=is_dedicated_reasoning(info.tag, info.name),
            )
        )
    return result


def _speed_known_for_all_fitting(cands: Iterable[_Cand]) -> bool:
    fitting = [c for c in cands if c.fits]
    return bool(fitting) and all(c.speed is not None for c in fitting)


def _sort_key(cand: _Cand, use_speed: bool) -> tuple:
    """`(cloud, dédié au raisonnement, ne tient pas, rang de débit, empreinte, nom, tag)`."""
    speed_rank = -(cand.speed or 0.0) if use_speed and cand.fits else 0.0
    return (
        cand.is_cloud,
        cand.reasoning,
        not cand.fits,
        speed_rank,
        cand.footprint_gb,
        cand.info.name.lower(),
        cand.tag,
    )


def _rank(cands: Sequence[_Cand]) -> tuple[list[_Cand], bool]:
    """Candidats triés par la règle (le premier est le défaut de `chat`) et si le débit mesuré
    a servi au tri (sinon l'empreinte)."""
    use_speed = _speed_known_for_all_fitting(cands)
    return sorted(cands, key=lambda c: _sort_key(c, use_speed)), use_speed


def cloud_judge_rank(model: str) -> tuple[int, str]:
    """Rang d'un modèle cloud comme juge (0 = le plus capable), puis le nom ; les autres après."""
    lowered = model.lower()
    if not lowered.startswith(CLOUD_JUDGE_DEMOTED):
        for rank, prefix in enumerate(CLOUD_JUDGE_PREFERENCE):
            if lowered.startswith(prefix):
                return rank, lowered
    return len(CLOUD_JUDGE_PREFERENCE), lowered


def _chat(ranked: list[_Cand], use_speed: bool) -> tuple[list[_Cand], str]:
    first = ranked[0]
    if first.is_cloud:
        return [first], (
            "Aucun modèle local n'est installé : le premier modèle cloud autorisé est proposé."
        )
    if not first.fits:
        return [first], (
            "Aucun modèle local ne tient en mémoire : le plus petit est proposé, "
            "il peut être lent ou échouer."
        )
    if use_speed:
        reason = "Le plus rapide des modèles locaux qui tiennent en mémoire (débit mesuré ici)."
    else:
        reason = (
            "Le plus léger des modèles locaux qui tiennent en mémoire "
            "(débit non mesuré sur ce poste : un modèle plus petit génère plus vite)."
        )
    if first.reasoning:
        reason += " Modèle dédié au raisonnement : ses réponses sont plus longues."
    return [first], reason


def _judge(ranked: list[_Cand], allow_cloud: bool) -> tuple[_Cand, str]:
    if allow_cloud:
        clouds = [c for c in ranked if c.is_cloud]
        if clouds:
            best = min(clouds, key=lambda c: cloud_judge_rank(c.info.name))
            return best, "Le modèle cloud le plus capable parmi ceux autorisés."
    measured = [
        c
        for c in ranked
        if not c.is_cloud and c.info.accuracy is not None and (c.speed or 0.0) > BENCH_MIN_SPEED_TPS
    ]
    if measured:
        pool = (
            [c for c in measured if c.fits and not c.weak_judge]
            or [c for c in measured if c.fits]
            or [c for c in measured if not c.weak_judge]
            or measured
        )
        best = min(pool, key=lambda c: (-(c.info.accuracy or 0.0), -(c.speed or 0.0), c.tag))
        return best, "Le plus précis des modèles locaux mesurés sur ce poste, assez rapide."
    fitting = [c for c in ranked if c.fits]
    if not fitting:
        smallest = next(c for c in ranked if not c.is_cloud)
        return smallest, (
            "Aucun modèle local ne tient en mémoire : le plus petit est proposé, "
            "il peut être lent ou échouer."
        )
    best = max(fitting, key=lambda c: (not c.weak_judge, _finite(c.footprint_gb), c.params_b or 0))
    reason = "Le plus gros modèle local qui tient en mémoire."
    if best.weak_judge:
        reason += (
            f" Moins de {JUDGE_MIN_PARAMS_B:g} milliards de paramètres actifs (ou inconnus) : "
            "ses notes sont à prendre avec prudence."
        )
    return best, reason


def _finite(value: float) -> float:
    return 0.0 if math.isinf(value) else value


def _arena(ranked: list[_Cand], judge: _Cand | None, use_speed: bool) -> tuple[list[_Cand], str]:
    fitting = [c for c in ranked if c.fits and not c.reasoning]
    if not fitting and any(c.fits for c in ranked):
        return [], (
            "Seuls des modèles dédiés au raisonnement tiennent en mémoire : l'Arène les écarte. "
            f"Installez au moins {ARENA_MIN_MODELS} autres modèles locaux qui tiennent."
        )
    others = [c for c in fitting if judge is None or c.tag != judge.tag]
    order = "rapides" if use_speed else "légers"
    if len(others) >= ARENA_MIN_MODELS:
        picked = others[:ARENA_MAX_MODELS]
        return picked, (
            f"Les {len(picked)} modèles locaux les plus {order} qui tiennent en mémoire, "
            "hors juge et hors modèles de raisonnement."
        )
    if len(fitting) >= ARENA_MIN_MODELS:
        picked = fitting[:ARENA_MIN_MODELS]
        return picked, (
            f"Les {ARENA_MIN_MODELS} modèles locaux les plus {order} qui tiennent en mémoire : "
            "le juge est repris faute d'un autre modèle."
        )
    if fitting:
        return fitting, (
            "Un seul modèle local tient en mémoire : l'Arène en demande au moins "
            f"{ARENA_MIN_MODELS}. Installez-en un autre ou libérez de la mémoire."
        )
    return [], (
        "Aucun modèle local ne tient en mémoire : l'Arène ne peut pas partir. "
        "Installez un modèle plus petit ou libérez de la mémoire."
    )


def _agent(ranked: list[_Cand]) -> tuple[_Cand, str] | None:
    pool = [
        c
        for c in ranked
        if not c.is_cloud
        and c.fits
        and not c.reasoning
        and c.info.tools_verified
        and c.params_b is not None
        and c.params_b >= AGENT_MIN_PARAMS_B
    ]
    if not pool:
        return None
    best = min(
        pool,
        key=lambda c: (-(c.info.accuracy or -1.0), -(c.speed or 0.0), c.footprint_gb, c.tag),
    )
    return best, (
        f"Le meilleur des modèles locaux qui tiennent en mémoire, aux outils vérifiés "
        f"et d'au moins {AGENT_MIN_PARAMS_B:g} milliards de paramètres actifs."
    )


def _rag(ranked: list[_Cand], use_speed: bool) -> tuple[_Cand, str] | None:
    pool = [
        c
        for c in ranked
        if not c.is_cloud
        and c.fits
        and not c.reasoning
        and c.params_b is not None
        and c.params_b >= RAG_MIN_PARAMS_B
    ]
    if not pool:
        return None
    speed = "le plus rapide" if use_speed else "le plus léger"
    return pool[0], (
        f"{speed.capitalize()} des modèles locaux qui tiennent en mémoire avec au moins "
        f"{RAG_MIN_PARAMS_B:g} milliards de paramètres actifs, pour répondre fidèlement "
        "aux extraits."
    )


def choose_default(
    models: Sequence[ModelInfo], purpose: Purpose, allow_cloud: bool = False
) -> ModelDefault:
    """Défaut de la règle pour un usage. Lève `no_model` sans modèle de conversation (local pour
    `arena`). `arena` et `agent` peuvent rendre moins de tags que demandé (voire aucun) : la
    raison le dit."""
    cands = _candidates(models, allow_cloud)
    if purpose == "arena":
        cands = [c for c in cands if not c.is_cloud]
    if not cands:
        raise AppError(
            "no_model",
            f"Aucun modèle de conversation disponible pour l'usage « {purpose} ».",
            purpose=purpose,
        )
    ranked, use_speed = _rank(cands)
    picked: list[_Cand]
    if purpose == "judge":
        best, reason = _judge(ranked, allow_cloud)
        picked = [best]
    elif purpose == "arena":
        judge, _ = _judge(ranked, False)
        picked, reason = _arena(ranked, judge, use_speed)
    elif purpose == "agent":
        found = _agent(ranked)
        if found is not None:
            picked, reason = [found[0]], found[1]
        else:
            picked = []
            reason = (
                "Aucun modèle local ne réunit les conditions de l'Agent (outils vérifiés, au "
                f"moins {AGENT_MIN_PARAMS_B:g} milliards de paramètres actifs, tient en mémoire, "
                "hors modèles de raisonnement) : aucun défaut n'est proposé. Un modèle choisi "
                "à la main peut échouer à appeler les outils."
            )
    elif purpose == "rag":
        found_rag = _rag(ranked, use_speed)
        if found_rag is not None:
            picked, reason = [found_rag[0]], found_rag[1]
        else:
            picked, base = _chat(ranked, use_speed)
            reason = (
                f"Aucun modèle local d'au moins {RAG_MIN_PARAMS_B:g} milliards de paramètres "
                f"actifs ne tient en mémoire : le modèle de conversation par défaut est proposé. "
                f"({base})"
            )
    else:
        picked, reason = _chat(ranked, use_speed)
    return ModelDefault(purpose=purpose, tags=[c.tag for c in picked], reason=reason, source="rule")


def _stored_tags(value: Any) -> list[str]:
    tags = value.get("tags") if isinstance(value, dict) else None
    return [t for t in tags if isinstance(t, str)] if isinstance(tags, list) else []


class ModelDefaults:
    """Défaut par usage : la préférence de l'UI si elle est encore valable, sinon la règle.

    Ne lit que l'API publique du registre (`list_models`) : aucune attente d'Ollama.
    """

    def __init__(self, registry: ModelCatalogLike, preferences: PreferenceStore) -> None:
        self._registry = registry
        self._preferences = preferences

    async def get(self, purpose: Purpose, allow_cloud: bool = False) -> ModelDefault:
        listed = await self._registry.list_models(allow_cloud=allow_cloud)
        stored = _stored_tags(self._preferences.get(PREFERENCE_KEY.format(purpose=purpose)))
        if stored:
            cands = _candidates(listed.models, allow_cloud)
            if purpose == "arena":  # l'Arène ne compare que des modèles locaux
                cands = [c for c in cands if not c.is_cloud]
            allowed = {c.tag for c in cands}
            kept = list(dict.fromkeys(t for t in stored if t in allowed))
            if purpose == "arena":
                kept = kept[:ARENA_MAX_MODELS] if len(kept) >= ARENA_MIN_MODELS else []
            else:
                kept = kept[:1]
            if kept:
                return ModelDefault(
                    purpose=purpose,
                    tags=kept,
                    reason="Votre choix enregistré pour cet usage.",
                    source="preference",
                )
        return choose_default(listed.models, purpose, allow_cloud)
