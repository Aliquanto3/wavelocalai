"""
Choix par défaut des modèles, adaptés à la machine : ordre des sélecteurs, modèle proposé,
juge par défaut et présélection de l'Arène.

Règle (fonctions pures, sans `streamlit`) :

- Modèles locaux d'abord, cloud en dernier (un tag distant servi par Ollama, `remote_host`,
  variante `:cloud` ou suffixe `-cloud`, compte comme cloud).
- Parmi les locaux, les modèles dédiés au raisonnement (reconnus à « thinking » ou
  « reasoning » dans leur tag ou leur nom, LFM 2.5 1.2B Thinking : leur raisonnement allonge
  la réponse réelle malgré leur débit ; les hybrides, capacité `thinking` du catalogue, n'en
  sont pas) passent après tous les autres, même ceux qui ne tiennent pas. Puis ceux qui
  tiennent en mémoire d'abord, le plus rapide en tête. Le débit départage selon une seule
  source à la fois, jamais deux mêlées dans une même comparaison :
  1. le débit prudent du benchmark de ce poste (src/core/benchmark_results.py), s'il mesure
     tous les locaux qui tiennent ;
  2. sinon `benchmark_stats.avg_tokens_per_second` de data/models.json (qui peut venir d'une
     autre machine), s'il en donne un pour tous les locaux qui tiennent ;
  3. sinon la plus petite empreinte sert d'indicateur de vitesse (un modèle plus petit
     génère plus vite sur une même machine) : un débit connu ne passe jamais devant un
     débit inconnu.
  Ceux qui ne tiennent pas suivent, du plus petit au plus gros (leur débit ne compte pas, ils
  n'ont pas besoin d'être mesurés) : si aucun ne tient, le premier proposé est le plus petit.
- « Outils vérifiés » (`tools_verified`) : d'après `tool_capability.success_rate` du benchmark
  de ce poste quand il l'a mesuré (≥ `AGENT_MIN_TOOL_SUCCESS`), d'après la capacité `tools`
  du catalogue sinon.
- Juge par défaut, dans cet ordre :
  1. cloud autorisé et modèles cloud proposés : le plus capable, selon
     `CLOUD_JUDGE_PREFERENCE` (jamais un juge cloud quand le cloud est désactivé) ;
  2. benchmark de ce poste (src/core/benchmark_results.py) : parmi les locaux installés
     mesurés à plus de `BENCH_MIN_SPEED_TPS` tokens/s (débit prudent), ceux qui tiennent en
     mémoire d'abord, le plus précis d'au moins `JUDGE_MIN_PARAMS_B` paramètres actifs ; le
     plus précis de tous seulement si aucun n'atteint ce plancher (note peu fiable).
     Précision égale : le plus rapide, puis le tag ;
  3. sinon (aucun benchmark de ce poste, aucun modèle assez rapide) : parmi les locaux qui
     tiennent, d'abord ceux dont la note est fiable, puis la plus grande empreinte
     (paramètres × précision), départagée par les paramètres actifs. Un 27B quantifié en
     1 bit ne passe pas devant un 9B en 3 bits, et un MoE n'est pas jugé sur ses paramètres
     totaux. Aucun local : pas de juge par défaut.
  Note peu fiable quand les paramètres actifs d'un juge local sont inférieurs à
  `JUDGE_MIN_PARAMS_B` ou inconnus.
- Modèle proposé par défaut de la page Agents (`agent_default`) : d'après le benchmark de ce
  poste, parmi les locaux installés, non dédiés au raisonnement, qui tiennent en mémoire,
  d'au moins `AGENT_MIN_PARAMS_B` paramètres actifs, aux outils vérifiés par le benchmark
  (`tool_capability.success_rate` ≥ `AGENT_MIN_TOOL_SUCCESS`) et à plus de
  `BENCH_MIN_SPEED_TPS` tokens/s : le plus précis, puis le plus rapide, puis le tag. Sans
  benchmark ou sans candidat : None (l'ordre de la page reste celui d'aujourd'hui).
- Arène : les 2 ou 3 locaux les plus rapides qui tiennent, hors juge par défaut (il ne note
  pas sa propre réponse) et hors modèles dédiés au raisonnement ; le juge n'y revient que
  s'il manque un modèle pour atteindre `ARENA_MIN_MODELS`. Le lancement exige au moins
  `ARENA_MIN_MODELS` modèles.

Empreinte en mémoire d'un modèle local, dans cet ordre :

1. `measured_loaded_gb` du catalogue versionné (`config/models_catalog.json`), mesurée ;
2. repli : taille du téléchargement × `SIZE_TO_LOADED` (même repli que
   `scripts/bench_here.py`), lue dans `size_gb` du catalogue versionné, puis de
   data/models.json, puis dans la taille renvoyée par Ollama ;
3. aucune estimation : empreinte inconnue, le modèle est considéré comme ne tenant pas.

« Tient en mémoire » : empreinte × `FIT_MARGIN` ≤ mémoire vive disponible −
`SYSTEM_RAM_BUFFER_GB` (la mémoire disponible inclut celle des modèles déjà chargés dans
Ollama, rajoutée par l'appelant).

Paramètres actifs : `params_act` (catalogue versionné, puis data/models.json), puis
`params_tot` (même ordre), puis `details.parameter_size` d'Ollama (un total) en dernier
recours.
"""

from __future__ import annotations

import copy
import json
import logging
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.core.config import SYSTEM_RAM_BUFFER_GB
from src.core.models_db import MODELS_DB
from src.core.utils import extract_params_billions

if TYPE_CHECKING:
    from src.core.benchmark_results import BenchScore

logger = logging.getLogger(__name__)

# Catalogue versionné, écrit par scripts/build_catalog.py (lecture seule ici).
CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "models_catalog.json"

# Mêmes valeurs que scripts/bench_here.py (un test vérifie qu'elles concordent) :
# marge de sécurité sur l'empreinte, et empreinte chargée estimée depuis la taille du
# téléchargement quand aucune mesure n'existe.
FIT_MARGIN = 1.10
SIZE_TO_LOADED = 1.25

# Sous ce nombre de paramètres actifs (en milliards), la note d'un juge est peu fiable.
JUDGE_MIN_PARAMS_B = 4.0

# Juge choisi d'après le benchmark de ce poste : débit prudent strictement supérieur.
BENCH_MIN_SPEED_TPS = 10.0

# Modèle par défaut des agents : paramètres actifs minimaux (en milliards) et taux de réussite
# des outils mesuré par le benchmark (seuil de `tools_validated` de scripts/benchmark_slm.py).
AGENT_MIN_PARAMS_B = 3.0
AGENT_MIN_TOOL_SUCCESS = 0.75

# Juges cloud, du plus capable au moins capable (préfixes de tag) ; les autres modèles cloud
# suivent par ordre alphabétique. Un fournisseur ajouté plus tard s'insère dans cette liste.
CLOUD_JUDGE_PREFERENCE = (
    "claude-sonnet-4",
    "gpt-4o",  # hors gpt-4o-mini (CLOUD_JUDGE_DEMOTED)
    "openai/gpt-oss-120b",  # Groq
    "mistral-large",
    "claude-3-5-sonnet",
    "claude-3-opus",
    "gpt-4-turbo",
    "mistral-medium",
    "llama-3.3-70b-versatile",  # Groq
)
# Préfixes rétrogradés parmi les autres modèles cloud (non classés), malgré un préfixe
# de la liste ci-dessus.
CLOUD_JUDGE_DEMOTED = ("gpt-4o-mini",)

# Modèle dédié au raisonnement (LFM 2.5 1.2B Thinking) : marqueur dans son tag ou son nom.
# Jamais proposé par défaut ni présélectionné dans l'Arène ; il reste sélectionnable.
REASONING_MARKERS = ("thinking", "reasoning")

# Comment le juge par défaut a été choisi (aide du sélecteur de juge).
JUDGE_BY_CLOUD = "cloud"
JUDGE_BY_BENCHMARK = "benchmark"
JUDGE_BY_FOOTPRINT = "footprint"
JUDGE_NONE_FITS = "none_fits"

# Nombre de modèles présélectionnés dans l'Arène (quand ils tiennent en mémoire).
ARENA_MIN_MODELS = 2
ARENA_MAX_MODELS = 3

# Suffixe des tags distants servis par Ollama (modèles « cloud » d'Ollama).
REMOTE_TAG_SUFFIX = "-cloud"
REMOTE_TAG_VARIANT = "cloud"

_BYTES_PER_GB = 1024**3


@dataclass(frozen=True)
class ModelChoice:
    """Ce que la règle sait d'un modèle proposé dans un sélecteur."""

    tag: str
    is_cloud: bool
    footprint_gb: float | None  # empreinte chargée (mesurée ou estimée), None si inconnue
    # Débit connu (tokens/s), None sinon : débit prudent du benchmark de ce poste quand il
    # mesure tous les locaux qui tiennent (rank_models), sinon celui de data/models.json. En
    # mode benchmark, un local non mesuré (il ne tient pas) passe à None, et un modèle cloud
    # garde le débit de data/models.json : sans effet sur le tri, le cloud étant en dernier.
    speed_tps: float | None
    params_b: float | None  # paramètres actifs, en milliards, None si inconnus
    fits: bool  # tient en mémoire (toujours False pour un modèle cloud)
    dedicated_reasoning: bool = False  # modèle dédié au raisonnement (« thinking » dans le nom)

    @property
    def weak_judge(self) -> bool:
        """Juge local de moins de ~4B paramètres actifs, ou de taille inconnue : note peu
        fiable."""
        if self.is_cloud:
            return False
        return self.params_b is None or self.params_b < JUDGE_MIN_PARAMS_B


# ---------------------------------------------------------------------------
# Lecture des catalogues
# ---------------------------------------------------------------------------


# Catalogues lus avec succès, par chemin. Un échec de lecture (fichier absent, en cours de
# réécriture) n'est pas mis en cache : la lecture suivante réessaie.
_CATALOG_CACHE: dict[Path, dict[str, dict[str, Any]]] = {}


def _read_catalog(path: Path) -> dict[str, dict[str, Any]] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("Catalogue de modèles illisible (%s) : %s", path, e)
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        logger.warning("Catalogue de modèles au format inattendu (%s) : ignoré", path)
        return None
    # Entrées qui ne sont pas des dictionnaires : ignorées une à une.
    return {name: entry for name, entry in models.items() if isinstance(entry, dict)}


def load_versioned_catalog(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Modèles du catalogue versionné ({nom: entrée}) ; vide s'il est absent, illisible ou
    au format inattendu. Renvoie une copie : le cache n'est jamais modifié par l'appelant."""
    path = path or CATALOG_PATH
    if path not in _CATALOG_CACHE:
        models = _read_catalog(path)
        if models is None:
            return {}
        _CATALOG_CACHE[path] = models
    return copy.deepcopy(_CATALOG_CACHE[path])


def base_tag(tag: str) -> str:
    """Tag sans la variante `:latest` (clé de correspondance)."""
    return tag.removesuffix(":latest")


def find_named_entry(
    tag: str, entries: Mapping[str, Any]
) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    """(nom, entrée) dont `ollama_tag` correspond au tag (variante `:latest` comprise) ;
    (None, None) sinon."""
    base = base_tag(tag)
    for name, info in entries.items():
        if not isinstance(info, dict):
            continue
        ollama_tag = info.get("ollama_tag")
        if isinstance(ollama_tag, str) and base_tag(ollama_tag) == base:
            return str(name), info
    return None, None


def find_entry(tag: str, entries: Mapping[str, Any]) -> dict[str, Any] | None:
    """Entrée dont `ollama_tag` correspond au tag (variante `:latest` comprise)."""
    return find_named_entry(tag, entries)[1]


# ---------------------------------------------------------------------------
# Faits sur un modèle
# ---------------------------------------------------------------------------


def parse_size_gb(value: Any) -> float:
    """Taille lisible (« 0.7 GB », « 1,2 Go », « 350 MB », 2.5) en Go ; 0.0 si illisible."""
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return 0.0
    s = value.lower().replace("≈", "").replace(",", ".").strip()
    factor = 1.0
    for unit, unit_factor in (("gb", 1.0), ("go", 1.0), ("mb", 1e-3), ("mo", 1e-3)):
        if s.endswith(unit):
            s, factor = s[: -len(unit)].strip(), unit_factor
            break
    try:
        return float(s) * factor
    except ValueError:
        return 0.0


def _positive_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if value > 0 else None


def estimate_footprint_gb(
    catalog_entry: Mapping[str, Any] | None,
    db_entry: Mapping[str, Any] | None = None,
    ollama_size_bytes: Any = None,
) -> float | None:
    """Empreinte chargée d'un modèle local : mesure, sinon repli documenté, sinon None."""
    measured = _positive_number((catalog_entry or {}).get("measured_loaded_gb"))
    if measured is not None:
        return measured
    for entry in (catalog_entry, db_entry):
        size = parse_size_gb((entry or {}).get("size_gb"))
        if size > 0:
            return size * SIZE_TO_LOADED
    size_bytes = _positive_number(ollama_size_bytes)
    if size_bytes is not None:
        return size_bytes / _BYTES_PER_GB * SIZE_TO_LOADED
    return None


def known_speed_tps(db_entry: Mapping[str, Any] | None) -> float | None:
    """Débit mesuré dans data/models.json (`benchmark_stats.avg_tokens_per_second`)."""
    stats = (db_entry or {}).get("benchmark_stats")
    if not isinstance(stats, dict):
        return None
    return _positive_number(stats.get("avg_tokens_per_second"))


def active_params_b(
    catalog_entry: Mapping[str, Any] | None,
    db_entry: Mapping[str, Any] | None = None,
    ollama_details: Mapping[str, Any] | None = None,
) -> float | None:
    """Paramètres actifs en milliards : `params_act` (catalogue versionné, puis
    data/models.json), puis `params_tot` (même ordre), puis `details.parameter_size`
    d'Ollama (un total, en dernier recours) ; None si inconnus."""
    entries = (catalog_entry or {}, db_entry or {})
    candidates = [e.get("params_act") for e in entries] + [e.get("params_tot") for e in entries]
    if isinstance(ollama_details, Mapping):
        candidates.append(ollama_details.get("parameter_size"))
    for raw in candidates:
        value = extract_params_billions(raw) if raw else 0.0
        if value > 0:
            return value
    return None


def is_remote_tag(model: Mapping[str, Any]) -> bool:
    """Tag distant servi par Ollama : ses données quittent la machine, il compte comme
    cloud. Reconnu à `remote_host` (absent après `model_dump()` d'ollama 0.6.2), à la
    variante `:cloud` (`glm-4.6:cloud`) ou au suffixe `-cloud` de la variante
    (`gpt-oss:120b-cloud`) ou du nom (`kimi-k2-cloud:latest`)."""
    if model.get("remote_host"):
        return True
    name, _, variant = str(model.get("model") or "").lower().partition(":")
    return (
        variant == REMOTE_TAG_VARIANT
        or variant.endswith(REMOTE_TAG_SUFFIX)
        or name.endswith(REMOTE_TAG_SUFFIX)
    )


def is_dedicated_reasoning(tag: str, *names: str | None) -> bool:
    """Modèle dédié au raisonnement : « thinking » ou « reasoning » dans son tag ou l'un de
    ses noms (LFM 2.5 1.2B Thinking). Un hybride (capacité `thinking` du catalogue, Qwen 3.5)
    n'en est pas un."""
    text = " ".join([tag, *(n for n in names if n)]).lower()
    return any(marker in text for marker in REASONING_MARKERS)


def usable_memory_gb(available_gb: float) -> float:
    """Mémoire utilisable par un modèle : disponible moins la réserve système."""
    return available_gb - SYSTEM_RAM_BUFFER_GB


def fits_in_memory(footprint_gb: float | None, available_gb: float) -> bool:
    """Empreinte connue qui, avec la marge `FIT_MARGIN`, tient dans la mémoire utilisable."""
    if footprint_gb is None:
        return False
    return footprint_gb * FIT_MARGIN <= usable_memory_gb(available_gb)


def describe_model(
    model: Mapping[str, Any],
    available_gb: float,
    is_cloud: bool,
    catalog: Mapping[str, Any],
    models_db: Mapping[str, Any],
    name: str | None = None,
) -> ModelChoice:
    """Faits d'un modèle au format de LLMProvider.list_models (`name` : nom affiché)."""
    tag = str(model["model"])
    is_cloud = is_cloud or is_remote_tag(model)
    catalog_name, catalog_entry = find_named_entry(tag, catalog)
    db_name, db_entry = find_named_entry(tag, models_db)
    reasoning = is_dedicated_reasoning(tag, name, catalog_name, db_name)
    details = model.get("details")
    params = active_params_b(
        catalog_entry, db_entry, details if isinstance(details, Mapping) else None
    )
    speed = known_speed_tps(db_entry)
    if is_cloud:
        return ModelChoice(
            tag, True, None, speed, params, fits=False, dedicated_reasoning=reasoning
        )
    footprint = estimate_footprint_gb(catalog_entry, db_entry, model.get("size"))
    return ModelChoice(
        tag,
        False,
        footprint,
        speed,
        params,
        fits=fits_in_memory(footprint, available_gb),
        dedicated_reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Règle
# ---------------------------------------------------------------------------


def _speed_known_for_all_fitting(choices: Iterable[ModelChoice]) -> bool:
    fitting = [c for c in choices if c.fits]
    return bool(fitting) and all(c.speed_tps is not None for c in fitting)


def _benchmark_covers_fitting(
    choices: Iterable[ModelChoice], benchmark: Mapping[str, BenchScore] | None
) -> bool:
    """Le benchmark de ce poste mesure tous les locaux qui tiennent (tag de base), modèles
    dédiés au raisonnement compris ; ceux qui ne tiennent pas n'ont pas besoin de l'être."""
    if not benchmark:
        return False
    fitting = [c for c in choices if c.fits]
    return bool(fitting) and all(base_tag(c.tag) in benchmark for c in fitting)


def sort_key(choice: ModelChoice, name: str = "", use_speed: bool = False) -> tuple:
    """`(is_cloud, dédié au raisonnement, not fits, rang de débit, empreinte, nom, tag)`.
    Le débit ne compte que pour les locaux qui tiennent, et seulement si `use_speed` (tous
    en ont un, d'une même source). Un modèle dédié au raisonnement passe après tous les
    autres locaux, qu'ils tiennent en mémoire ou non : il n'est proposé en premier que s'il
    est le seul local."""
    footprint = choice.footprint_gb if choice.footprint_gb is not None else math.inf
    speed_rank = -(choice.speed_tps or 0.0) if use_speed and choice.fits else 0.0
    return (
        choice.is_cloud,
        choice.dedicated_reasoning,
        not choice.fits,
        speed_rank,
        footprint,
        name,
        choice.tag,
    )


def rank_models(
    models: Iterable[Mapping[str, Any]],
    available_gb: float,
    cloud_types: tuple[str, ...] = ("cloud",),
    names: Mapping[str, str] | None = None,
    catalog: Mapping[str, Any] | None = None,
    models_db: Mapping[str, Any] | None = None,
    benchmark: Mapping[str, BenchScore] | None = None,
) -> list[ModelChoice]:
    """
    Modèles (format LLMProvider.list_models) triés par la règle ; le premier est le modèle
    proposé par défaut. `available_gb` : mémoire vive disponible, modèles déjà chargés dans
    Ollama compris. `names` (tag → nom affiché) départage les égalités. `catalog` et
    `models_db` remplacent le catalogue versionné et data/models.json (tests).

    `benchmark` ({tag de base : BenchScore}, benchmark de ce poste) : s'il mesure tous les
    locaux qui tiennent, chaque local prend son débit prudent (None s'il n'est pas mesuré :
    il ne tient pas, son débit ne compte pas) et le tri se fait sur ce débit. Sinon, rien ne
    change : data/models.json s'il donne un débit pour chacun, sinon l'empreinte. Les deux
    sources ne se mêlent jamais.
    """
    catalog = load_versioned_catalog() if catalog is None else catalog
    models_db = MODELS_DB if models_db is None else models_db
    names = names or {}
    choices = [
        describe_model(
            m,
            available_gb,
            m.get("type") in cloud_types,
            catalog,
            models_db,
            name=names.get(str(m["model"])),
        )
        for m in models
        if m.get("model")
    ]
    if _benchmark_covers_fitting(choices, benchmark):
        # Local non mesuré (il ne tient pas) : getattr(None, …) donne None.
        choices = [
            (
                c
                if c.is_cloud
                else replace(
                    c, speed_tps=getattr(benchmark.get(base_tag(c.tag)), "speed_tps", None)
                )
            )
            for c in choices
        ]
        use_speed = True
    else:
        use_speed = _speed_known_for_all_fitting(choices)
    return sorted(choices, key=lambda c: sort_key(c, names.get(c.tag, c.tag), use_speed))


def tools_verified(
    tag: str,
    capabilities: Iterable[str] | None,
    benchmark: Mapping[str, BenchScore] | None,
) -> bool:
    """Outils vérifiés : d'après le benchmark de ce poste quand il a mesuré les outils de ce
    modèle (`tool_success` ≥ `AGENT_MIN_TOOL_SUCCESS`, tag de base, variante `:latest`
    comprise), même si le catalogue dit l'inverse ; sinon d'après la capacité `tools` du
    catalogue (`capabilities`)."""
    score = benchmark.get(base_tag(tag)) if benchmark else None
    if score is not None and score.tool_success is not None:
        return score.tool_success >= AGENT_MIN_TOOL_SUCCESS
    return "tools" in (capabilities or ())


def default_model(ranked: list[ModelChoice]) -> ModelChoice | None:
    """Modèle proposé par défaut : le premier de la liste triée."""
    return ranked[0] if ranked else None


@dataclass(frozen=True)
class JudgeDefault:
    """Juge par défaut et la façon dont il a été choisi (`JUDGE_BY_*`, None sans juge)."""

    choice: ModelChoice | None
    reason: str | None


def cloud_judge_rank(tag: str) -> tuple[int, str]:
    """Rang d'un modèle cloud comme juge : position de son préfixe dans
    `CLOUD_JUDGE_PREFERENCE` (0 = le plus capable), puis le tag ; les autres après, par
    ordre alphabétique."""
    lowered = tag.lower()
    if not lowered.startswith(CLOUD_JUDGE_DEMOTED):
        for rank, prefix in enumerate(CLOUD_JUDGE_PREFERENCE):
            if lowered.startswith(prefix):
                return rank, lowered
    return len(CLOUD_JUDGE_PREFERENCE), lowered


def _cloud_judge(ranked: list[ModelChoice]) -> ModelChoice | None:
    clouds = [c for c in ranked if c.is_cloud]
    return min(clouds, key=lambda c: cloud_judge_rank(c.tag)) if clouds else None


def benchmark_judge(
    ranked: list[ModelChoice], benchmark: Mapping[str, BenchScore] | None
) -> ModelChoice | None:
    """Juge d'après le benchmark de ce poste : parmi les locaux installés mesurés à plus de
    `BENCH_MIN_SPEED_TPS` tokens/s, le plus précis d'au moins `JUDGE_MIN_PARAMS_B`
    paramètres actifs ; le plus précis de tous si aucun n'atteint ce plancher. Ceux qui
    tiennent en mémoire d'abord : fiable qui tient, puis qui tient, puis fiable, puis tous.
    Précision égale : le plus rapide, puis le tag. None sans benchmark ou sans modèle assez
    rapide."""
    if not benchmark:
        return None
    scored = []
    for choice in ranked:
        if choice.is_cloud:
            continue
        score = benchmark.get(base_tag(choice.tag))
        if score is not None and score.speed_tps > BENCH_MIN_SPEED_TPS:
            scored.append((choice, score))
    if not scored:
        return None
    pool = (
        [(c, s) for c, s in scored if c.fits and not c.weak_judge]
        or [(c, s) for c, s in scored if c.fits]
        or [(c, s) for c, s in scored if not c.weak_judge]
        or scored
    )
    best, _ = min(pool, key=lambda cs: (-cs[1].precision, -cs[1].speed_tps, cs[0].tag))
    return best


def agent_default(
    ranked: list[ModelChoice], benchmark: Mapping[str, BenchScore] | None
) -> ModelChoice | None:
    """Modèle proposé par défaut sur la page Agents (Agent seul et Équipe), d'après le
    benchmark de ce poste. Candidats : locaux installés, non dédiés au raisonnement, qui
    tiennent en mémoire, d'au moins `AGENT_MIN_PARAMS_B` paramètres actifs, aux outils
    vérifiés par le benchmark (`tool_success` ≥ `AGENT_MIN_TOOL_SUCCESS`) et mesurés à plus
    de `BENCH_MIN_SPEED_TPS` tokens/s. Le plus précis (même précision que le juge), puis le
    plus rapide, puis le tag. None sans benchmark ou sans candidat."""
    if not benchmark:
        return None
    candidates = []
    for choice in ranked:
        if choice.is_cloud or choice.dedicated_reasoning or not choice.fits:
            continue
        if choice.params_b is None or choice.params_b < AGENT_MIN_PARAMS_B:
            continue
        score = benchmark.get(base_tag(choice.tag))
        if score is None or score.speed_tps <= BENCH_MIN_SPEED_TPS:
            continue
        if score.tool_success is None or score.tool_success < AGENT_MIN_TOOL_SUCCESS:
            continue
        candidates.append((choice, score))
    if not candidates:
        return None
    best, _ = min(candidates, key=lambda cs: (-cs[1].precision, -cs[1].speed_tps, cs[0].tag))
    return best


def _footprint_judge(ranked: list[ModelChoice]) -> ModelChoice | None:
    fitting = [c for c in ranked if c.fits]
    if not fitting:
        return next((c for c in ranked if not c.is_cloud), None)
    return max(fitting, key=lambda c: (not c.weak_judge, c.footprint_gb or 0.0, c.params_b or 0.0))


def choose_judge(
    ranked: list[ModelChoice],
    benchmark: Mapping[str, BenchScore] | None = None,
    allow_cloud: bool = False,
) -> JudgeDefault:
    """
    Juge par défaut et sa raison, dans cet ordre :

    1. `allow_cloud` (cloud autorisé) et modèles cloud proposés : le plus capable
       (`CLOUD_JUDGE_PREFERENCE`) ;
    2. `benchmark` de ce poste ({tag de base : BenchScore}) : `benchmark_judge` ;
    3. règle de l'empreinte : parmi les locaux qui tiennent, d'abord ceux dont la note est
       fiable (≥ `JUDGE_MIN_PARAMS_B` paramètres actifs connus), puis la plus grande
       empreinte, départagée par les paramètres actifs. Un MoE à grosse empreinte et peu de
       paramètres actifs ne passe donc pas devant un juge fiable. Aucun local ne tient : le
       plus petit local. Aucun local : pas de juge.
    """
    if allow_cloud:
        cloud = _cloud_judge(ranked)
        if cloud is not None:
            return JudgeDefault(cloud, JUDGE_BY_CLOUD)
    judge = benchmark_judge(ranked, benchmark)
    if judge is not None:
        return JudgeDefault(judge, JUDGE_BY_BENCHMARK)
    judge = _footprint_judge(ranked)
    if judge is None:
        return JudgeDefault(None, None)
    return JudgeDefault(judge, JUDGE_BY_FOOTPRINT if judge.fits else JUDGE_NONE_FITS)


def default_judge(
    ranked: list[ModelChoice],
    benchmark: Mapping[str, BenchScore] | None = None,
    allow_cloud: bool = False,
) -> ModelChoice | None:
    """Juge par défaut (`choose_judge`) ; toujours local quand `allow_cloud` est faux."""
    return choose_judge(ranked, benchmark, allow_cloud).choice


def arena_preselection(
    ranked: list[ModelChoice],
    judge: ModelChoice | None = None,
    limit: int = ARENA_MAX_MODELS,
) -> list[str]:
    """
    Tags présélectionnés dans l'Arène : les locaux les plus rapides qui tiennent, au plus
    `limit`, hors juge (il ne note pas sa propre réponse) et hors modèles dédiés au
    raisonnement. Le juge ne revient que s'il manque un modèle pour atteindre
    `ARENA_MIN_MODELS`. Jamais un modèle qui ne tient pas, un modèle cloud ni un modèle dédié
    au raisonnement : s'il en reste moins de `ARENA_MIN_MODELS`, la présélection est
    incomplète et le lancement reste désactivé jusqu'au choix d'un second modèle.
    """
    fitting = [c.tag for c in ranked if c.fits and not c.dedicated_reasoning]
    judge_tag = judge.tag if judge else None
    others = [t for t in fitting if t != judge_tag]
    if len(others) >= ARENA_MIN_MODELS:
        return others[:limit]
    return fitting[: min(limit, ARENA_MIN_MODELS)]
