"""« Quel modèle pour quel usage » : les références du banc (`qb.results/1`) par usage (story 5.8).

Tout se décide ici (AD-20) : le groupe des meilleurs, les marques « installé » et « autre version »,
les modèles que « Comparer ces modèles » présélectionne. Le front met en forme et ne calcule ni rang
ni groupe. Lecture seule, depuis le fichier déjà lu (`BenchReferences`) et la liste du registre :
aucun appel d'Ollama (AD-15).

- Un usage sans modèle classé n'a pas de carte. Un score `null`, ou provisoire (`writing`), laisse le
  modèle « non classé » pour cet usage ; il figure dans `unranked`, sans score, jamais 0.
- Groupe des meilleurs : le meilleur score, puis tous les modèles dont l'intervalle atteint celui du
  meilleur (`ci_high` >= `ci_low` du meilleur). Un intervalle absent vaut le score seul. Pas de rang :
  les membres du groupe sont triés par nom.
- Poste de référence : le PC pro du banc ; sans lui, débit et énergie sont inconnus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from typing import Literal

from pydantic import BaseModel

from wavelocalai.models.bench_results import (
    BenchMachine,
    BenchMatch,
    LoadedBench,
    usage_score,
)
from wavelocalai.models.classify import base_tag

SOURCE = "slm-quality-bench"
COMPARE_MAX = 4  # l'Arène compare quatre modèles au plus

# Les usages que le schéma publie, dans l'ordre d'affichage : (clé, libellé, ce que mesure le score).
USAGES: tuple[tuple[str, str, str, str], ...] = (
    (
        "reasoning",
        "Raisonnement",
        "Résoudre un problème en plusieurs étapes, sans se perdre en chemin.",
        "Part de problèmes résolus",
    ),
    (
        "instructions",
        "Consignes",
        "Suivre à la lettre un format, une longueur ou un ton demandés.",
        "Part de consignes respectées",
    ),
    (
        "tools",
        "Appel d'outils",
        "Choisir le bon outil et remplir ses arguments sans se tromper.",
        "Part d'appels d'outils corrects",
    ),
    (
        "extraction",
        "Extraction",
        "Retrouver des informations précises dans un texte et les rendre structurées.",
        "Part d'informations extraites correctement",
    ),
    (
        "rag",
        "Réponse sur documents",
        "Répondre à partir d'extraits fournis, sans rien inventer.",
        "Part de réponses justes sur documents",
    ),
    (
        "abstention",
        "Savoir s'abstenir",
        "Dire qu'on ne sait pas quand la réponse n'est pas dans les sources.",
        "Part d'abstentions justifiées",
    ),
    (
        "writing",
        "Rédaction",
        "Rédiger un texte clair et utile en français.",
        "Part de textes jugés réussis",
    ),
)

NO_USAGE_REASON = "Le banc n'a classé aucun modèle pour aucun usage dans les résultats publiés."
NONE_INSTALLED = "Aucun modèle de ce groupe n'est installé sur ce poste."
OLLAMA_DOWN = "Modèles installés non vérifiés\u00a0: Ollama ne répond pas."

Mark = Literal["installed", "other_version"]


@dataclass(frozen=True)
class InstalledModel:
    """Un modèle de conversation installé sur ce poste (liste du registre)."""

    tag: str
    digest: str | None


class ReferenceMachine(BaseModel):
    id: str
    label: str
    gpu: str | None
    vram_gb: float | None
    ram_gb: float | None


class ReferenceEntry(BaseModel):
    tag: str  # tag du banc
    name: str
    params_active_b: float | None
    score: (
        float | None
    )  # fraction de 0 à 1 (le front l'affiche en pourcentage) ; `null` : non classé
    ci_low: float | None
    ci_high: float | None
    group: Literal["best", "other"] | None  # `null` : non classé
    decode_tok_s: float | None  # sur le poste de référence ; `null` sans mesure
    energy_wh_per_1k_tokens: float | None  # seulement si `status = "measured"`
    installed: Mark | None  # `null` : pas installé, ou Ollama arrêté
    installed_tag: str | None  # le tag tel qu'installé sur ce poste


class CompareTarget(BaseModel):
    tags: list[str]  # modèles du groupe installés, par nom, quatre au plus
    reason: str | None  # pourquoi la liste est vide


class UsageReference(BaseModel):
    id: str
    label: str
    description: str
    measure: str  # « Part de … » : en tête du score
    best_count: int
    entries: list[ReferenceEntry]  # groupe des meilleurs par nom, puis les autres, puis non classés
    compare: CompareTarget


class TopScore(BaseModel):
    usage: str
    usage_label: str
    measure: str
    tag: str
    name: str
    score: float


class References(BaseModel):
    available: bool
    reason: str | None = None
    reason_code: str | None = None
    source: str = SOURCE
    bench_version: str | None = None
    published: str | None = None  # date (AAAA-MM-JJ) de la campagne la plus récente
    reference_machine: ReferenceMachine | None = None
    ollama_up: bool = True
    top: TopScore | None = None
    usages: list[UsageReference] = []


def _gb(mib: int | None) -> float | None:
    return None if mib is None else round(mib / 1024, 1)


def _machine_view(machine: BenchMachine) -> ReferenceMachine:
    return ReferenceMachine(
        id=machine.id,
        label=machine.label,
        gpu=machine.gpu,
        vram_gb=_gb(machine.vram_mib),
        ram_gb=_gb(machine.ram_mib),
    )


def _published(bench: LoadedBench) -> str | None:
    moments = [c.ended_at for c in (bench.file.campaigns if bench.file else []) if c.ended_at]
    if not moments:
        return None
    return max(moments).astimezone(UTC).date().isoformat()


def _round(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


@dataclass
class _Candidate:
    tag: str
    name: str
    match: BenchMatch
    mark: Mark | None
    installed_tag: str | None


def _installed_marks(
    bench: LoadedBench, installed: list[InstalledModel]
) -> dict[str, tuple[Mark, str, str | None]]:
    """Par tag de base du banc : (marque, tag installé, empreinte installée). Les mêmes poids
    l'emportent sur une autre version, puis le tag par ordre alphabétique."""
    found: dict[str, tuple[Mark, str, str | None]] = {}
    for model in sorted(installed, key=lambda m: m.tag):
        match = bench.find(model.tag, model.digest)
        if match is None or not model.digest:
            continue
        mark: Mark = "installed" if match.version == "exact" else "other_version"
        key = base_tag(match.model.tag)
        previous = found.get(key)
        if previous is None or (mark == "installed" and previous[0] != "installed"):
            found[key] = (mark, model.tag, model.digest)
    return found


def _candidates(
    bench: LoadedBench, installed: list[InstalledModel], ollama_up: bool
) -> list[_Candidate]:
    marks = _installed_marks(bench, installed) if ollama_up else {}
    seen: set[str] = set()
    out: list[_Candidate] = []
    for model in bench.file.models if bench.file else []:
        key = base_tag(model.tag)
        if key in seen:
            continue
        seen.add(key)
        mark = marks.get(key)
        match = bench.find(model.tag, mark[2] if mark else None)
        if match is None:
            continue
        out.append(
            _Candidate(
                tag=match.model.tag,
                name=match.model.name or match.model.tag,
                match=match,
                mark=mark[0] if mark else None,
                installed_tag=mark[1] if mark else None,
            )
        )
    return out


def _entry(
    bench: LoadedBench,
    candidate: _Candidate,
    usage: str,
    order: list[str],
    reference_id: str | None,
) -> ReferenceEntry:
    """La ligne d'un modèle pour un usage : score du premier poste (la référence d'abord) qui en
    publie un, débit et énergie du poste de référence seulement."""
    scope = None
    for machine_id in order:
        result = bench.best_result(candidate.match, machine_id, usage)
        if result is not None:
            scope = usage_score(result, usage)
            break
    rate = energy = None
    if reference_id is not None:
        reference = bench.best_result(candidate.match, reference_id)
        if reference is not None:
            rate = reference.speed.decode_tok_s
            if reference.energy.status == "measured":
                energy = reference.energy.gpu_wh_per_1k_tokens
    return ReferenceEntry(
        tag=candidate.tag,
        name=candidate.name,
        params_active_b=candidate.match.model.params_active_b,
        score=None if scope is None else round(scope.score, 4),
        ci_low=None if scope is None else _round(scope.ci_low, 4),
        ci_high=None if scope is None else _round(scope.ci_high, 4),
        group=None,
        decode_tok_s=_round(rate, 1),
        energy_wh_per_1k_tokens=_round(energy, 3),
        installed=candidate.mark,
        installed_tag=candidate.installed_tag,
    )


def _interval(entry: ReferenceEntry) -> tuple[float, float]:
    assert entry.score is not None
    low = entry.score if entry.ci_low is None else entry.ci_low
    high = entry.score if entry.ci_high is None else entry.ci_high
    return low, high


def _leader(ranked: list[ReferenceEntry]) -> ReferenceEntry:
    """Le meilleur score ; à égalité, le premier par nom."""
    return min(ranked, key=lambda e: (-(e.score or 0), e.name.casefold()))


def _compare(group: list[ReferenceEntry], ollama_up: bool) -> CompareTarget:
    if not ollama_up:
        return CompareTarget(tags=[], reason=OLLAMA_DOWN)
    tags = [e.installed_tag for e in group if e.installed_tag]
    if not tags:
        return CompareTarget(tags=[], reason=NONE_INSTALLED)
    return CompareTarget(tags=tags[:COMPARE_MAX], reason=None)


def _usage(
    bench: LoadedBench,
    candidates: list[_Candidate],
    spec: tuple[str, str, str, str],
    order: list[str],
    reference_id: str | None,
    ollama_up: bool,
) -> UsageReference | None:
    key, label, description, measure = spec
    entries = [_entry(bench, c, key, order, reference_id) for c in candidates]
    ranked = [e for e in entries if e.score is not None]
    if not ranked:
        return None
    best = _leader(ranked)
    floor = _interval(best)[0]
    for entry in ranked:
        entry.group = "best" if _interval(entry)[1] >= floor else "other"
    group = sorted((e for e in ranked if e.group == "best"), key=lambda e: e.name.casefold())
    others = sorted(
        (e for e in ranked if e.group == "other"),
        key=lambda e: (-(e.score or 0), e.name.casefold()),
    )
    unranked = sorted(
        (e for e in entries if e.score is None and e.tag in _measured(candidates)),
        key=lambda e: e.name.casefold(),
    )
    return UsageReference(
        id=key,
        label=label,
        description=description,
        measure=measure,
        best_count=len(group),
        entries=[*group, *others, *unranked],
        compare=_compare(group, ollama_up),
    )


def _measured(candidates: list[_Candidate]) -> set[str]:
    """Les modèles pour lesquels le banc a au moins un résultat."""
    return {c.tag for c in candidates if c.match.results}


def build_usage_references(
    bench: LoadedBench, installed: list[InstalledModel], *, ollama_up: bool
) -> References:
    if not bench.available:
        return References(
            available=False,
            reason=bench.reason,
            reason_code=bench.reason_code,
            ollama_up=ollama_up,
        )
    reference = next((m for m in bench.machines if m.is_pc_pro), None)
    reference_id = reference.id if reference else None
    order = ([reference_id] if reference_id else []) + [
        m.id for m in bench.machines if m.id != reference_id
    ]
    candidates = _candidates(bench, installed, ollama_up)
    usages = [
        view
        for spec in USAGES
        if (view := _usage(bench, candidates, spec, order, reference_id, ollama_up)) is not None
    ]
    if not usages:
        return References(
            available=False,
            reason=NO_USAGE_REASON,
            reason_code="no_usage",
            bench_version=bench.bench_version,
            published=_published(bench),
            ollama_up=ollama_up,
        )
    top: TopScore | None = None
    for view in usages:
        leader = _leader([e for e in view.entries if e.score is not None])
        if top is None or (leader.score or 0) > top.score:
            top = TopScore(
                usage=view.id,
                usage_label=view.label,
                measure=view.measure,
                tag=leader.tag,
                name=leader.name,
                score=leader.score or 0,
            )
    return References(
        available=True,
        bench_version=bench.bench_version,
        published=_published(bench),
        reference_machine=_machine_view(reference) if reference else None,
        ollama_up=ollama_up,
        top=top,
        usages=usages,
    )
