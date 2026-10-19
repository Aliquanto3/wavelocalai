"""Résultats publiés du banc `qb.results/1` : lecture seule, jamais par le réseau (AD-22).

Le fichier `benchmarks/slm-quality/slm-quality-results.json` est écrit par `scripts/sync_slm_results.py`
(Action GitHub, validé contre le schéma de la release) ; l'app ne le modifie jamais. Module partagé :
la fiche d'un modèle (story 5.6) et les écrans qui lisent les références (stories 5.7 et 5.8) passent
par `BenchReferences`.

- Lu une fois au premier accès, puis relu quand le fichier change (date et taille).
- Modèles pydantic `extra="ignore"` : un champ ajouté au schéma sans changer `qb.results/1` est ignoré.
- `schema` doit valoir `qb.results/1`, sinon les références sont indisponibles avec une raison.
- `results[]` se joint à `models[]` sur `(model, digest)` ; un modèle installé correspond par
  `(tag, digest)`, à défaut par tag, signalé comme « autre version » (jamais un score attribué à
  d'autres poids sans le dire).
- Un `null` reste `None` (inconnu), jamais 0.
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from wavelocalai.models.classify import base_tag

logger = logging.getLogger("wavelocalai.models")

SCHEMA = "qb.results/1"
RELATIVE_PATH = Path("benchmarks") / "slm-quality" / "slm-quality-results.json"
# Pistes par ordre de préférence : sans raisonnement d'abord (la mesure de référence).
TRACK_ORDER = ("think_off", "think_on")
# Un poste « PC pro » : 16 Go de mémoire vive (à 2 Go près, la mémoire vue par le système est un peu
# moindre) et aucune carte graphique.
PC_PRO_RAM_MIB = (14 * 1024, 18 * 1024)

Reason = Literal["missing", "unreadable", "schema", "format"]
REASON_TEXTS: dict[str, str] = {
    "missing": "Le fichier des résultats du banc n'est pas synchronisé sur ce poste.",
    "unreadable": "Le fichier des résultats du banc est illisible.",
    "schema": f"Le fichier des résultats du banc n'a pas le format attendu (schéma {SCHEMA}).",
    "format": "Le fichier des résultats du banc est incomplet ou mal formé.",
}


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class BenchMachine(_Lenient):
    id: str
    label: str
    gpu: str | None = None
    vram_mib: int | None = None
    ram_mib: int | None = None
    os: str | None = None

    @property
    def is_pc_pro(self) -> bool:
        low, high = PC_PRO_RAM_MIB
        return self.gpu is None and self.ram_mib is not None and low <= self.ram_mib <= high


class BenchCampaign(_Lenient):
    id: str
    status: str | None = None
    first_line_at: str | None = None
    last_line_at: str | None = None

    @property
    def ended_at(self) -> datetime | None:
        """Fin de la campagne (dernière ligne, à défaut la première) ; `None` si absente ou illisible."""
        for text in (self.last_line_at, self.first_line_at):
            if not text:
                continue
            try:
                moment = datetime.fromisoformat(text)
            except ValueError:
                continue
            return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
        return None


def _campaign_ranks(campaigns: list[BenchCampaign]) -> dict[str, int]:
    """Rang de chaque campagne, la plus récente la plus haute : par date de fin publiée, puis par
    place dans `campaigns[]` (une campagne sans date passe avant celles qui en ont une)."""
    floor = datetime.min.replace(tzinfo=UTC)
    order = sorted(enumerate(campaigns), key=lambda item: (item[1].ended_at or floor, item[0]))
    return {campaign.id: rank for rank, (_, campaign) in enumerate(order)}


class BenchModel(_Lenient):
    tag: str
    digest: str
    name: str | None = None
    editor: str | None = None
    family: str | None = None
    moe: bool | None = None
    params_total_b: float | None = None
    params_active_b: float | None = None
    context_length: int | None = None
    capabilities: list[str] = Field(default_factory=list)


class QualityScope(_Lenient):
    score: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n_units: int | None = None
    coverage: float | None = None
    status: str | None = None  # `writing` seulement : `final` ou `provisional`


class Quality(_Lenient):
    overall: QualityScope | None = Field(default=None, alias="global")
    usages: dict[str, QualityScope] = Field(default_factory=dict)


class Speed(_Lenient):
    decode_tok_s: float | None = None
    prefill_tok_s: float | None = None
    load_time_ms: float | None = None


class Memory(_Lenient):
    ram_baseline_mib: int | None = None
    ram_peak_mib: int | None = None
    vram_baseline_mib: int | None = None
    vram_peak_mib: int | None = None
    model_size_mib: float | None = None
    model_vram_mib: float | None = None
    validated_ctx: int | None = None


class Energy(_Lenient):
    status: str = "unavailable"  # `measured`, `unvalidated` ou `unavailable`
    gpu_power_avg_w: float | None = None
    gpu_wh_per_1k_tokens: float | None = None


class BenchResult(_Lenient):
    model: str
    digest: str
    machine: str
    campaign: str | None = None
    track: str = "think_off"
    complete: bool = False
    quality: Quality = Field(default_factory=Quality)
    speed: Speed = Field(default_factory=Speed)
    memory: Memory = Field(default_factory=Memory)
    energy: Energy = Field(default_factory=Energy)


class ResultsFile(_Lenient):
    schema_name: str = Field(alias="schema")
    bench_version: str | None = None
    campaigns: list[BenchCampaign] = Field(default_factory=list)
    machines: list[BenchMachine] = Field(default_factory=list)
    models: list[BenchModel] = Field(default_factory=list)
    results: list[BenchResult] = Field(default_factory=list)


def normalize_digest(digest: str | None) -> str:
    """Empreinte sans préfixe `sha256:`, en minuscules : `""` si absente."""
    return (digest or "").removeprefix("sha256:").strip().lower()


def same_digest(left: str | None, right: str | None) -> bool:
    """Deux empreintes désignent les mêmes poids : égales, ou l'une est le début de l'autre (l'identifiant
    court d'Ollama, 12 caractères au moins)."""
    a, b = normalize_digest(left), normalize_digest(right)
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 12 and long.startswith(short)


@dataclass(frozen=True)
class BenchMatch:
    model: BenchModel
    # `exact` : même empreinte ; `other_version` : même tag, autre empreinte ; `unknown` : aucune
    # empreinte à comparer (modèle pas installé).
    version: Literal["exact", "other_version", "unknown"]
    results: tuple[BenchResult, ...]


def _order(track: str) -> int:
    return TRACK_ORDER.index(track) if track in TRACK_ORDER else len(TRACK_ORDER)


class LoadedBench:
    """Un instantané du fichier, indexé ; `available` faux porte la raison."""

    def __init__(self, file: ResultsFile | None, reason: Reason | None = None) -> None:
        self.file = file
        self.reason_code: Reason | None = reason
        self._campaign_rank = _campaign_ranks(file.campaigns) if file else {}
        self._machines = {m.id: m for m in file.machines} if file else {}
        self._models: dict[str, list[BenchModel]] = {}
        # Résultats groupés par tag de base : `find` ne parcourt que ceux du modèle (une fiche, ou
        # chaque modèle de `GET /api/models`), jamais tout le fichier.
        self._results: dict[str, list[BenchResult]] = {}
        for result in file.results if file else []:
            self._results.setdefault(base_tag(result.model), []).append(result)
        for model in file.models if file else []:
            self._models.setdefault(base_tag(model.tag), []).append(model)

    @property
    def available(self) -> bool:
        return self.file is not None

    @property
    def reason(self) -> str | None:
        return None if self.reason_code is None else REASON_TEXTS[self.reason_code]

    @property
    def bench_version(self) -> str | None:
        return self.file.bench_version if self.file else None

    @property
    def machines(self) -> list[BenchMachine]:
        return list(self._machines.values())

    def machine(self, machine_id: str) -> BenchMachine | None:
        return self._machines.get(machine_id)

    def find(self, tag: str, digest: str | None = None) -> BenchMatch | None:
        """Les mesures publiées d'un modèle : même empreinte si on la donne, sinon même tag."""
        candidates = self._models.get(base_tag(tag))
        if not candidates:
            return None
        if digest:
            exact = [m for m in candidates if same_digest(m.digest, digest)]
            version: Literal["exact", "other_version", "unknown"] = (
                "exact" if exact else "other_version"
            )
        else:
            exact, version = [], "unknown"
        model = (exact or candidates)[-1]
        results = tuple(
            r
            for r in self._results.get(base_tag(model.tag), ())
            if same_digest(r.digest, model.digest)
        )
        return BenchMatch(model=model, version=version, results=results)

    def best_result(self, match: BenchMatch, machine_id: str) -> BenchResult | None:
        """Le résultat à montrer pour un poste : piste sans raisonnement d'abord, puis complet, puis
        la campagne la plus récente."""
        rows = [r for r in match.results if r.machine == machine_id]
        if not rows:
            return None
        return min(
            rows,
            key=lambda r: (
                _order(r.track),
                not r.complete,
                -self._campaign_rank.get(r.campaign or "", -1),
            ),
        )

    def accuracy(self, tag: str, digest: str | None) -> float | None:
        """Précision globale d'un modèle installé : médiane des scores `quality.global` des résultats
        de **ses** poids (même empreinte ; jamais ceux d'une autre version), piste sans raisonnement
        d'abord, résultats complets d'abord. `None` sans mesure publiée."""
        if not digest:
            return None
        match = self.find(tag, digest)
        if match is None or match.version != "exact":
            return None
        for track in TRACK_ORDER:
            for only_complete in (True, False):
                scores = [
                    r.quality.overall.score
                    for r in match.results
                    if r.track == track
                    and (r.complete or not only_complete)
                    and r.quality.overall is not None
                    and r.quality.overall.score is not None
                ]
                if scores:
                    return round(float(statistics.median(scores)), 4)
        return None


class BenchReferences:
    """Le fichier des résultats, relu quand il change. Les appels sont courts (un `stat`) ; la lecture
    d'un fichier modifié bloque : l'appeler dans un fil (`asyncio.to_thread`) depuis la boucle."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._stamp: tuple[int, int] | None = None
        self._loaded: LoadedBench | None = None
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def current(self) -> LoadedBench:
        try:
            stat = self._path.stat()
            stamp: tuple[int, int] | None = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = None
        with self._lock:
            if self._loaded is None or stamp != self._stamp:
                self._loaded = self._load() if stamp is not None else LoadedBench(None, "missing")
                self._stamp = stamp
            return self._loaded

    def _load(self) -> LoadedBench:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Résultats du banc illisibles (%s) : %s", self._path, exc)
            return LoadedBench(None, "unreadable")
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            return LoadedBench(None, "schema")
        try:
            return LoadedBench(ResultsFile.model_validate(data))
        except ValidationError as exc:
            logger.warning("Résultats du banc mal formés (%s) : %s", self._path, exc)
            return LoadedBench(None, "format")
