"""
Benchmark de ce poste, lu dans les résultats versionnés (`benchmarks/results/*.json`, écrits
par `scripts/bench_here.py export`, lecture seule ici) : source unique côté app de la
précision et du débit mesurés sur cette machine.

- Poste : reconnu par la même empreinte que `scripts/machine_profile.machine_id` (hash de
  `hostname|machine|processor`, sans le libellé). Le fichier `<libellé>-<empreinte>.json`
  (ou `<empreinte>.json`) est celui de ce poste. Aucun fichier : pas de benchmark.
- Précision d'un modèle : moyenne de `quality_scores.reasoning_avg` et
  `quality_scores.instruction_following_avg`.
- Débit prudent : le plus bas entre `avg_tokens_per_second` et
  `runs.tokens_per_second.mean` (Granite 4.2 8B mesure 10,41 puis 5,05 tokens/s).
- Outils : `tool_capability.success_rate` (0 à 1), None s'il manque ou est illisible.
- Nom → tag : `ollama_tag` de l'entrée, sinon celui du catalogue versionné
  (`config/models_catalog.json`, clé = nom du modèle).

`data/models.json` n'est jamais lu ici : il peut venir d'une autre machine. Rien n'est
mesuré : le fichier est seulement lu. Un fichier illisible ou incomplet donne un benchmark
vide (ou partiel), avec un avertissement dans le journal, jamais une exception.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import platform
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core import model_defaults

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parents[2] / "benchmarks" / "results"


@dataclass(frozen=True)
class BenchScore:
    """Ce que le benchmark de ce poste dit d'un modèle."""

    precision: float  # moyenne de raisonnement et suivi d'instructions (0 à 1)
    speed_tps: float  # débit prudent, en tokens/s
    tool_success: float | None = None  # `tool_capability.success_rate` (0 à 1), None inconnu


def machine_digest() -> str:
    """Empreinte de ce poste : même calcul que `scripts/machine_profile.machine_id(None)`
    (un test vérifie qu'elles concordent), sans importer `scripts/`."""
    seed = f"{socket.gethostname()}|{platform.machine()}|{platform.processor()}"
    return hashlib.sha256(seed.encode()).hexdigest()[:8]


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("Résultats de benchmark illisibles (%s) : %s", path, e)
        return None


def find_results_file(results_dir: Path | None = None, digest: str | None = None) -> Path | None:
    """Fichier de résultats de ce poste (`<libellé>-<empreinte>.json` ou
    `<empreinte>.json`) ; None s'il n'y en a pas. Plusieurs (libellés différents) : le plus
    récent selon `exported_at`, puis le nom."""
    results_dir = results_dir or RESULTS_DIR
    digest = digest or machine_digest()
    try:
        matches = sorted(
            p
            for p in results_dir.glob("*.json")
            if p.stem == digest or p.stem.endswith(f"-{digest}")
        )
    except OSError as e:
        logger.warning("Dossier des résultats de benchmark illisible (%s) : %s", results_dir, e)
        return None
    if len(matches) <= 1:
        return matches[0] if matches else None

    def exported_at(path: Path) -> str:
        data = _read_json(path)
        value = data.get("exported_at") if isinstance(data, dict) else None
        return value if isinstance(value, str) else ""

    return max(matches, key=lambda p: (exported_at(p), p.name))


def _number(value: Any) -> float | None:
    """Nombre fini, sinon None (NaN et infini, acceptés par json.loads, compris)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _precision(entry: Mapping[str, Any]) -> float | None:
    scores = entry.get("quality_scores")
    if not isinstance(scores, Mapping):
        return None
    reasoning = _number(scores.get("reasoning_avg"))
    following = _number(scores.get("instruction_following_avg"))
    if reasoning is None or following is None:
        return None
    return round((reasoning + following) / 2, 6)  # égalités exactes (0,93 = 0,93)


def _cautious_speed(entry: Mapping[str, Any]) -> float | None:
    runs = entry.get("runs")
    tps = runs.get("tokens_per_second") if isinstance(runs, Mapping) else None
    candidates = [
        _number(entry.get("avg_tokens_per_second")),
        _number(tps.get("mean")) if isinstance(tps, Mapping) else None,
    ]
    speeds = [s for s in candidates if s is not None and s > 0]
    return min(speeds) if speeds else None


def _tool_success(entry: Mapping[str, Any]) -> float | None:
    """`tool_capability.success_rate`, entre 0 et 1 ; None s'il manque ou est illisible."""
    capability = entry.get("tool_capability")
    if not isinstance(capability, Mapping):
        return None
    rate = _number(capability.get("success_rate"))
    return rate if rate is not None and 0.0 <= rate <= 1.0 else None


def _tag_of(name: str, entry: Mapping[str, Any], catalog: Mapping[str, Any]) -> str | None:
    tag = entry.get("ollama_tag")
    if isinstance(tag, str) and tag:
        return tag
    catalog_entry = catalog.get(name)
    tag = catalog_entry.get("ollama_tag") if isinstance(catalog_entry, Mapping) else None
    return tag if isinstance(tag, str) and tag else None


def parse_results(data: Any, catalog: Mapping[str, Any]) -> dict[str, BenchScore]:
    """{tag de base (sans `:latest`) : BenchScore} depuis le contenu d'un fichier de
    résultats (section `models`). Entrée sans précision, sans débit ou sans tag : ignorée.
    Format inattendu : vide, avec un avertissement."""
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        logger.warning("Résultats de benchmark au format inattendu : section `models` absente")
        return {}
    scores: dict[str, BenchScore] = {}
    skipped = []
    for name, entry in models.items():
        if not isinstance(entry, Mapping):
            skipped.append(str(name))
            continue
        tag = _tag_of(str(name), entry, catalog)
        precision = _precision(entry)
        speed = _cautious_speed(entry)
        if tag is None or precision is None or speed is None:
            skipped.append(str(name))
            continue
        scores[model_defaults.base_tag(tag)] = BenchScore(
            precision, speed, tool_success=_tool_success(entry)
        )
    if skipped:
        logger.warning(
            "Résultats de benchmark incomplets, modèles ignorés : %s", ", ".join(skipped)
        )
    return scores


# Benchmarks lus avec succès, par fichier (avec le catalogue versionné). Un échec de lecture
# ou un résultat vide n'est pas mis en cache.
_CACHE: dict[Path, dict[str, BenchScore]] = {}


def load_machine_benchmark(
    results_dir: Path | None = None,
    catalog: Mapping[str, Any] | None = None,
    digest: str | None = None,
) -> dict[str, BenchScore]:
    """Benchmark de ce poste, {tag de base : BenchScore} ; vide si ce poste n'a pas de
    fichier de résultats ou s'il est illisible. Ne lève jamais."""
    try:
        path = find_results_file(results_dir, digest)
        if path is None:
            return {}
        if catalog is None and path in _CACHE:
            return dict(_CACHE[path])
        data = _read_json(path)
        if data is None:
            return {}
        if catalog is not None:  # catalogue fourni (tests) : pas de cache
            return parse_results(data, catalog)
        scores = parse_results(data, model_defaults.load_versioned_catalog())
        if scores:  # un catalogue illisible vide le résultat : relu la fois suivante
            _CACHE[path] = scores
        return dict(scores)
    except Exception as e:  # le benchmark n'est qu'une aide au choix par défaut
        logger.warning("Benchmark de ce poste ignoré : %s", e)
        return {}
