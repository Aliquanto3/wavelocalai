"""Fiche d'un modèle (story 5.6) : caractéristiques, « Pourquoi ce débit ? » et « Sur d'autres postes ».

Tout ce qui est chiffré est calculé ici, côté serveur (AD-20) : l'écran met en forme et n'explique
rien lui-même. Les mesures publiées viennent de `bench_results.py` (AD-22) : un `null` reste `None`
(« inconnu » à l'écran), une fraction reste de 0 à 1, l'énergie n'est rendue que si `status` vaut
`measured`. Rien ici ne lit Ollama ni le réseau (AD-15) : la fiche sort du cache du registre.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from wavelocalai.models.bench_results import BenchMatch, BenchResult, LoadedBench

NBSP = " "
MAX_MACHINES = 6  # postes de référence listés au plus (le banc en publie trois)
MIB_PER_GB = 1024.0

Architecture = Literal["dense", "moe"]
CardOrigin = Literal["local", "cloud"]


@dataclass(frozen=True)
class CardSource:
    """Ce que le registre sait d'un modèle (installé, au catalogue ou cloud), sans mise en forme."""

    tag: str
    name: str
    editor: str | None
    origin: CardOrigin
    installed: bool
    in_catalog: bool
    digest: str | None
    architecture: Architecture | None
    params_total_b: float | None
    params_active_b: float | None
    quantization: str | None
    context_length: int | None
    license: str | None
    tools_verified: bool | None
    reasoning: bool | None
    size_gb: float | None  # poids du modèle (taille installée, sinon téléchargement du catalogue)
    needed_gb: float | None
    required_gb: float | None
    short_gb: float | None
    fits: bool | None
    throughput_tps: float | None


class CardMemory(BaseModel):
    model_gb: float | None  # taille du modèle mesurée par le banc
    gpu_fraction: float | None  # part du modèle logée en mémoire vidéo (0 à 1) ; `null` sans GPU
    ram_peak_gb: float | None
    ram_fraction: float | None  # pic de mémoire vive sur la mémoire du poste (0 à 1)
    validated_ctx: int | None


class CardEnergy(BaseModel):
    status: str  # `measured`, `unvalidated` ou `unavailable`
    wh_per_1k_tokens: float | None = None  # seulement si `status == "measured"`
    power_avg_w: float | None = None  # idem


class ReferenceRow(BaseModel):
    machine_id: str
    label: str
    gpu: str | None
    vram_gb: float | None
    ram_gb: float | None
    pc_pro: bool  # le PC pro : 16 Go de mémoire vive, sans carte graphique
    measured: bool  # le banc a un résultat pour ce modèle sur ce poste
    track: str | None
    complete: bool | None
    decode_tok_s: float | None
    prefill_tok_s: float | None
    load_time_s: float | None
    memory: CardMemory
    energy: CardEnergy


class CardReferences(BaseModel):
    available: bool
    reason: str | None = None  # pourquoi les références sont indisponibles
    bench_version: str | None = None
    # `exact` : mêmes poids que le modèle installé ; `other_version` : même tag, autre empreinte
    # (mesures indicatives) ; `unknown` : modèle pas installé, aucune empreinte à comparer ;
    # `not_published` : le banc ne le mesure pas.
    version: Literal["exact", "other_version", "unknown", "not_published"] | None = None
    pc_pro_published: bool = False  # un poste « PC pro » figure parmi les postes publiés
    rows: list[ReferenceRow] = []


class CardWhy(BaseModel):
    measured_tps: float | None  # débit mesuré sur ce poste (médiane des runs), `null` sans run
    bandwidth_gb_s: float | None = None  # non mesurée sur ce poste : jamais devinée
    vram_gb: float | None  # mémoire vidéo de ce poste, `null` si inconnue ou sans GPU
    lines: list[str]  # les phrases de l'explication, dans l'ordre


class ModelCard(BaseModel):
    tag: str
    name: str
    editor: str | None
    origin: CardOrigin
    installed: bool
    in_catalog: bool
    architecture: Architecture | None
    params_total_b: float | None
    params_active_b: float | None
    quantization: str | None
    context_length: int | None
    license: str | None
    tools_verified: bool | None
    reasoning: bool | None
    size_gb: float | None
    needed_gb: float | None
    required_gb: float | None
    short_gb: float | None
    fits: bool | None
    throughput_tps: float | None
    why: CardWhy | None  # `null` : modèle pas installé ou cloud, rien à expliquer
    references: CardReferences


def _gb(value: float | None, digits: int = 1) -> str:
    """« 2,7 », « 4 », « 0,35 » : décimale française, sans zéro inutile."""
    if value is None:
        return "?"
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".") if digits else f"{value:.0f}"
    return (text or "0").replace(".", ",")


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _gb_from_mib(value: float | None) -> float | None:
    return None if value is None else round(value / MIB_PER_GB, 2)


def _fraction(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator or denominator <= 0:
        return None
    return round(min(max(numerator / denominator, 0.0), 1.0), 4)


_BEFORE_PUNCTUATION = re.compile(r" (?=[:;!?])|(?<=\d) (?=Go|tokens/s)")


def _typography(text: str) -> str:
    """Espace insécable avant « : ; ! ? » et entre un nombre et son unité."""
    return _BEFORE_PUNCTUATION.sub(NBSP, text)


def why_lines(source: CardSource, *, vram_gb: float | None) -> list[str]:
    """Les phrases de « Pourquoi ce débit ? » : paramètres actifs, quantification, mémoire vidéo et
    mémoire vive, puis le débit mesuré sur ce poste. Aucune valeur inventée : ce qui manque est dit."""
    lines: list[str] = []
    total, active = source.params_total_b, source.params_active_b
    if source.architecture == "moe":
        if active is not None and total is not None:
            lines.append(
                f"Modèle à mélange d'experts{NBSP}: {_gb(total)} milliards de paramètres au total, "
                f"mais seulement {_gb(active)} actifs à chaque token. Le débit dépend des "
                "paramètres actifs, pas du total."
            )
        else:
            lines.append(
                "Modèle à mélange d'experts : le nombre de paramètres actifs n'est pas publié, "
                "le débit ne peut pas être rattaché à une taille précise."
            )
    elif active is not None:
        lines.append(
            f"Le modèle active {_gb(active)} milliards de paramètres à chaque token{NBSP}: c'est "
            "la quantité de poids lue en mémoire pour produire un token, et elle borne le débit."
        )
    else:
        lines.append(
            "Le nombre de paramètres de ce modèle est inconnu : on ne peut pas dire quelle "
            "quantité de poids est lue à chaque token."
        )
    if source.quantization and source.size_gb is not None:
        weights = f"environ {_gb(source.size_gb)} Go de poids"
        if source.architecture == "moe":
            lines.append(
                f"Quantification {source.quantization} : {weights} au total, dont une petite "
                "partie lue à chaque token."
            )
        else:
            lines.append(
                f"Quantification {source.quantization} : {weights} à lire pour chaque token produit."
            )
    elif source.quantization:
        lines.append(f"Quantification {source.quantization} : la taille des poids n'est pas connue.")
    else:
        lines.append("La quantification de ce modèle est inconnue.")
    if vram_gb is None:
        lines.append(
            "Ce poste n'a pas de mémoire vidéo mesurée : les poids sont lus dans la mémoire vive, "
            "dont la bande passante borne le débit."
        )
    elif source.needed_gb is None:
        lines.append(
            f"La carte graphique de ce poste a {_gb(vram_gb)}{NBSP}Go de mémoire vidéo ; "
            "l'empreinte du modèle est inconnue, on ne sait pas s'il y tient en entier."
        )
    elif source.needed_gb <= vram_gb:
        lines.append(
            f"La carte graphique de {_gb(vram_gb)}{NBSP}Go garde tout le modèle en mémoire vidéo, "
            "dont la bande passante est bien supérieure à celle de la mémoire vive."
        )
    else:
        lines.append(
            f"Le modèle dépasse la mémoire vidéo de {_gb(vram_gb)}{NBSP}Go : une partie des couches "
            "reste en mémoire vive, plus lente, ce qui limite le débit."
        )
    lines.append(
        "La bande passante mémoire de ce poste n'est pas mesurée : seul le débit observé est "
        "donné, pas un plafond théorique."
    )
    if source.throughput_tps is not None:
        lines.append(
            f"Sur ce poste, ces facteurs donnent le débit mesuré de {_gb(source.throughput_tps, 0)}"
            f"{NBSP}tokens/s."
        )
    else:
        lines.append(
            "Aucun débit n'est encore mesuré sur ce poste pour ce modèle : lancez une conversation "
            "avec lui."
        )
    return [_typography(line) for line in lines]


def _row(bench: LoadedBench, match: BenchMatch, machine) -> ReferenceRow:
    result: BenchResult | None = bench.best_result(match, machine.id)
    ram_peak = result.memory.ram_peak_mib if result else None
    has_gpu = machine.gpu is not None
    energy = result.energy if result else None
    measured_energy = energy is not None and energy.status == "measured"
    return ReferenceRow(
        machine_id=machine.id,
        label=machine.label,
        gpu=machine.gpu,
        vram_gb=_gb_from_mib(machine.vram_mib),
        ram_gb=_gb_from_mib(machine.ram_mib),
        pc_pro=machine.is_pc_pro,
        measured=result is not None,
        track=result.track if result else None,
        complete=result.complete if result else None,
        decode_tok_s=_round(result.speed.decode_tok_s) if result else None,
        prefill_tok_s=_round(result.speed.prefill_tok_s) if result else None,
        load_time_s=(
            _round(result.speed.load_time_ms / 1000.0)
            if result and result.speed.load_time_ms is not None
            else None
        ),
        memory=CardMemory(
            model_gb=_gb_from_mib(result.memory.model_size_mib) if result else None,
            gpu_fraction=(
                _fraction(result.memory.model_vram_mib, result.memory.model_size_mib)
                if result and has_gpu
                else None
            ),
            ram_peak_gb=_gb_from_mib(ram_peak),
            ram_fraction=_fraction(ram_peak, machine.ram_mib),
            validated_ctx=result.memory.validated_ctx if result else None,
        ),
        energy=CardEnergy(
            status=energy.status if energy else "unavailable",
            wh_per_1k_tokens=_round(energy.gpu_wh_per_1k_tokens, 3) if measured_energy else None,
            power_avg_w=_round(energy.gpu_power_avg_w, 1) if measured_energy else None,
        ),
    )


def build_references(bench: LoadedBench, source: CardSource) -> CardReferences:
    """« Sur d'autres postes » : une ligne par poste publié par le banc, le PC pro d'abord."""
    if not bench.available:
        return CardReferences(available=False, reason=bench.reason)
    match = bench.find(source.tag, source.digest if source.installed else None)
    version = "not_published" if match is None else match.version
    machines = sorted(
        bench.machines,
        key=lambda m: (not m.is_pc_pro, m.vram_mib or 0, m.ram_mib or 0, m.label),
    )[:MAX_MACHINES]
    rows = [] if match is None else [_row(bench, match, machine) for machine in machines]
    return CardReferences(
        available=True,
        bench_version=bench.bench_version,
        version=version,
        pc_pro_published=any(m.is_pc_pro for m in bench.machines),
        rows=rows,
    )


def build_card(source: CardSource, bench: LoadedBench, *, vram_gb: float | None) -> ModelCard:
    why = None
    if source.installed and source.origin == "local":
        why = CardWhy(
            measured_tps=_round(source.throughput_tps, 1),
            vram_gb=_round(vram_gb),
            lines=why_lines(source, vram_gb=vram_gb),
        )
    return ModelCard(
        tag=source.tag,
        name=source.name,
        editor=source.editor,
        origin=source.origin,
        installed=source.installed,
        in_catalog=source.in_catalog,
        architecture=source.architecture,
        params_total_b=source.params_total_b,
        params_active_b=source.params_active_b,
        quantization=source.quantization,
        context_length=source.context_length,
        license=source.license,
        tools_verified=source.tools_verified,
        reasoning=source.reasoning,
        size_gb=source.size_gb,
        needed_gb=source.needed_gb,
        required_gb=source.required_gb,
        short_gb=source.short_gb,
        fits=source.fits,
        throughput_tps=_round(source.throughput_tps, 1),
        why=why,
        references=build_references(bench, source),
    )
