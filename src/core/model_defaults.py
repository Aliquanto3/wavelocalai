"""
Choix par défaut des modèles, adaptés à la machine : ordre des sélecteurs, modèle proposé,
juge par défaut et présélection de l'Arène.

Règle (fonctions pures, sans `streamlit`) :

- Modèles locaux d'abord, cloud en dernier (un tag distant servi par Ollama, `remote_host`,
  variante `:cloud` ou suffixe `-cloud`, compte comme cloud).
- Parmi les locaux, ceux qui tiennent en mémoire d'abord, le plus rapide en tête. Le débit
  mesuré (`benchmark_stats.avg_tokens_per_second` de data/models.json) ne départage que si
  tous les locaux qui tiennent en ont un ; sinon la plus petite empreinte sert d'indicateur
  de vitesse (un modèle plus petit génère plus vite sur une même machine) : un débit connu
  ne passe jamais devant un débit inconnu. Ceux qui ne tiennent pas suivent, du plus petit
  au plus gros : si aucun ne tient, le premier proposé est le plus petit.
- Juge par défaut : parmi les locaux qui tiennent, d'abord ceux dont la note est fiable,
  puis la plus grande empreinte (paramètres × précision), départagée par les paramètres
  actifs. Un 27B quantifié en 1 bit ne passe pas devant un 9B en 3 bits, et un MoE n'est pas
  jugé sur ses paramètres totaux. Note peu fiable quand les paramètres actifs d'un juge
  local sont inférieurs à `JUDGE_MIN_PARAMS_B` ou inconnus. Aucun local : pas de juge par
  défaut.
- Arène : les 2 ou 3 locaux les plus rapides qui tiennent, hors juge par défaut (il ne note
  pas sa propre réponse) ; le juge n'y revient que s'il manque un modèle pour atteindre
  `ARENA_MIN_MODELS`. Le lancement exige au moins `ARENA_MIN_MODELS` modèles.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.config import SYSTEM_RAM_BUFFER_GB
from src.core.models_db import MODELS_DB
from src.core.utils import extract_params_billions

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
    speed_tps: float | None  # débit connu (tokens/s), None sinon
    params_b: float | None  # paramètres actifs, en milliards, None si inconnus
    fits: bool  # tient en mémoire (toujours False pour un modèle cloud)

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


def _base_tag(tag: str) -> str:
    return tag.removesuffix(":latest")


def find_entry(tag: str, entries: Mapping[str, Any]) -> dict[str, Any] | None:
    """Entrée dont `ollama_tag` correspond au tag (variante `:latest` comprise)."""
    base = _base_tag(tag)
    for info in entries.values():
        if not isinstance(info, dict):
            continue
        ollama_tag = info.get("ollama_tag")
        if isinstance(ollama_tag, str) and _base_tag(ollama_tag) == base:
            return info
    return None


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
) -> ModelChoice:
    """Faits d'un modèle au format de LLMProvider.list_models."""
    tag = str(model["model"])
    is_cloud = is_cloud or is_remote_tag(model)
    catalog_entry = find_entry(tag, catalog)
    db_entry = find_entry(tag, models_db)
    details = model.get("details")
    params = active_params_b(
        catalog_entry, db_entry, details if isinstance(details, Mapping) else None
    )
    speed = known_speed_tps(db_entry)
    if is_cloud:
        return ModelChoice(tag, True, None, speed, params, fits=False)
    footprint = estimate_footprint_gb(catalog_entry, db_entry, model.get("size"))
    return ModelChoice(
        tag, False, footprint, speed, params, fits=fits_in_memory(footprint, available_gb)
    )


# ---------------------------------------------------------------------------
# Règle
# ---------------------------------------------------------------------------


def _speed_known_for_all_fitting(choices: Iterable[ModelChoice]) -> bool:
    fitting = [c for c in choices if c.fits]
    return bool(fitting) and all(c.speed_tps is not None for c in fitting)


def sort_key(choice: ModelChoice, name: str = "", use_speed: bool = False) -> tuple:
    """`(is_cloud, not fits, rang de débit, empreinte, nom, tag)`. Le débit ne compte que
    pour les locaux qui tiennent, et seulement si `use_speed` (tous en ont un)."""
    footprint = choice.footprint_gb if choice.footprint_gb is not None else math.inf
    speed_rank = -(choice.speed_tps or 0.0) if use_speed and choice.fits else 0.0
    return (choice.is_cloud, not choice.fits, speed_rank, footprint, name, choice.tag)


def rank_models(
    models: Iterable[Mapping[str, Any]],
    available_gb: float,
    cloud_types: tuple[str, ...] = ("cloud",),
    names: Mapping[str, str] | None = None,
    catalog: Mapping[str, Any] | None = None,
    models_db: Mapping[str, Any] | None = None,
) -> list[ModelChoice]:
    """
    Modèles (format LLMProvider.list_models) triés par la règle ; le premier est le modèle
    proposé par défaut. `available_gb` : mémoire vive disponible, modèles déjà chargés dans
    Ollama compris. `names` (tag → nom affiché) départage les égalités. `catalog` et
    `models_db` remplacent le catalogue versionné et data/models.json (tests).
    """
    catalog = load_versioned_catalog() if catalog is None else catalog
    models_db = MODELS_DB if models_db is None else models_db
    names = names or {}
    choices = [
        describe_model(m, available_gb, m.get("type") in cloud_types, catalog, models_db)
        for m in models
        if m.get("model")
    ]
    use_speed = _speed_known_for_all_fitting(choices)
    return sorted(choices, key=lambda c: sort_key(c, names.get(c.tag, c.tag), use_speed))


def default_model(ranked: list[ModelChoice]) -> ModelChoice | None:
    """Modèle proposé par défaut : le premier de la liste triée."""
    return ranked[0] if ranked else None


def default_judge(ranked: list[ModelChoice]) -> ModelChoice | None:
    """Juge par défaut, toujours local : parmi les locaux qui tiennent, d'abord ceux dont la
    note est fiable (≥ `JUDGE_MIN_PARAMS_B` paramètres actifs connus), puis la plus grande
    empreinte, départagée par les paramètres actifs. Un MoE à grosse empreinte et peu de
    paramètres actifs ne passe donc pas devant un juge fiable. Aucun local ne tient : le plus
    petit local. Aucun local : None (jamais un juge cloud par défaut)."""
    fitting = [c for c in ranked if c.fits]
    if not fitting:
        return next((c for c in ranked if not c.is_cloud), None)
    return max(fitting, key=lambda c: (not c.weak_judge, c.footprint_gb or 0.0, c.params_b or 0.0))


def arena_preselection(
    ranked: list[ModelChoice],
    judge: ModelChoice | None = None,
    limit: int = ARENA_MAX_MODELS,
) -> list[str]:
    """
    Tags présélectionnés dans l'Arène : les locaux les plus rapides qui tiennent, au plus
    `limit`, hors juge (il ne note pas sa propre réponse). Le juge ne revient que s'il
    manque un modèle pour atteindre `ARENA_MIN_MODELS`. Jamais un modèle qui ne tient pas
    ni un modèle cloud : si moins de `ARENA_MIN_MODELS` tiennent, la présélection est
    incomplète et le lancement reste désactivé jusqu'au choix d'un second modèle.
    """
    fitting = [c.tag for c in ranked if c.fits]
    judge_tag = judge.tag if judge else None
    others = [t for t in fitting if t != judge_tag]
    if len(others) >= ARENA_MIN_MODELS:
        return others[:limit]
    return fitting[: min(limit, ARENA_MIN_MODELS)]
