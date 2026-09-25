#!/usr/bin/env python3
"""Fusionne les résultats de plusieurs machines et les compare.

    python scripts/merge_results.py                          # tableau comparatif (débit)
    python scripts/merge_results.py --metric quality_scores.reasoning_avg
    python scripts/merge_results.py --campaign vendor        # campagne « au mieux »
    python scripts/merge_results.py --csv                    # écrit benchmarks/comparison.csv

Chaque machine publie son propre fichier dans benchmarks/results/ : un fichier
par machine, donc aucun conflit de fusion git. Le script refuse de comparer en
silence des mesures produites par des versions différentes du benchmark.

Pour les modèles qu'une machine n'a mesurés qu'en vitesse (bench_speed_only.py),
le débit et le TTFT de la campagne standard sont remplacés par ceux de la mesure
de vitesse seule ; leurs scores de qualité restent ceux de la campagne standard.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "benchmarks" / "results"
CSV_PATH = ROOT / "benchmarks" / "comparison.csv"

CAMPAIGNS = {"standard": "models", "vendor": "models_vendor"}

# (chemin dans les statistiques, libellé, décimales)
FIELDS = [
    ("avg_tokens_per_second", "tok/s", 1),
    ("gpu_offload_pct", "% GPU", 0),
    ("model_memory_at_max_ctx_gb", "Go", 2),
    ("avg_ttft_ms", "TTFT ms", 0),
    ("max_validated_ctx", "ctx", 0),
    ("quality_scores.reasoning_avg", "raisonnement", 2),
    ("quality_scores.instruction_following_avg", "instructions", 2),
]
DIGITS = {path: digits for path, _label, digits in FIELDS}

# Champs que la mesure de vitesse seule remplace, et leur nom par palier.
SPEED_ONLY_FIELDS = {"avg_tokens_per_second": "tokens_per_second",
                     "avg_ttft_ms": "time_to_first_token_ms"}


def load_all() -> list[dict]:
    if not RESULTS_DIR.exists():
        raise SystemExit(f"Aucun résultat : {RESULTS_DIR} n'existe pas.")
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS_DIR.glob("*.json"))]
    if not runs:
        raise SystemExit(f"Aucun fichier dans {RESULTS_DIR}.")
    return runs


def lookup(stats: dict, path: str):
    for key in path.split("."):
        stats = stats.get(key) if isinstance(stats, dict) else None
    return stats if isinstance(stats, (int, float)) and not isinstance(stats, bool) else None


def value(run: dict, campaign: str, model: str, path: str) -> tuple[float | None, bool]:
    """Valeur d'un champ, et vrai si elle vient de la mesure de vitesse seule."""
    speed_only = run.get("models_speed_only", {}).get(model)
    if campaign == "standard" and speed_only and path in SPEED_ONLY_FIELDS:
        # Moyenne des paliers, comme avg_tokens_per_second en campagne standard.
        means = [level[SPEED_ONLY_FIELDS[path]]["mean"]
                 for level in speed_only["by_context"].values()
                 if level.get(SPEED_ONLY_FIELDS[path])]
        if means:
            return round(sum(means) / len(means), 2), True
    return lookup(run.get(CAMPAIGNS[campaign], {}).get(model, {}), path), False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", action="store_true",
                    help="Écrire benchmarks/comparison.csv (les deux campagnes, tous les champs)")
    ap.add_argument("--metric", default="avg_tokens_per_second",
                    help="Métrique comparée dans le tableau, chemin pointé accepté "
                         "(défaut : avg_tokens_per_second)")
    ap.add_argument("--campaign", choices=CAMPAIGNS, default="standard",
                    help="Campagne comparée dans le tableau (défaut : standard)")
    args = ap.parse_args()

    runs = load_all()
    commits = {r.get("benchmark_commit", "inconnu")[:8] for r in runs}
    dirty = [r["machine"]["machine_id"] for r in runs if r.get("benchmark_dirty")]

    print(f"{len(runs)} machines : " + ", ".join(
        f"{r['machine']['machine_id']} ({r['machine']['mode']}, "
        f"{r['machine']['vram_gb'] or r['machine']['ram_gb']} Go)" for r in runs))

    if len(commits) > 1:
        print(f"\n⚠️  Versions de benchmark différentes ({', '.join(sorted(commits))}).")
        print("   Les scores de qualité ne sont pas comparables entre ces machines :")
        print("   réexécutez avec la même version avant de conclure.")
    if dirty:
        print(f"⚠️  Code modifié localement sur : {', '.join(dirty)}")

    # Tableau : une ligne par modèle, une colonne par machine
    matrix: dict[str, dict[str, tuple[float, bool]]] = defaultdict(dict)
    for run in runs:
        mid = run["machine"]["machine_id"]
        for model in run.get(CAMPAIGNS[args.campaign], {}):
            v, speed_only = value(run, args.campaign, model, args.metric)
            if v is not None:
                matrix[model][mid] = (v, speed_only)

    digits = DIGITS.get(args.metric, 1)
    machines = [r["machine"]["machine_id"] for r in runs]
    width = max((len(m) for m in matrix), default=10) + 2
    print(f"\n{args.metric} — campagne {args.campaign}\n")
    print("modèle".ljust(width) + "".join(m[:14].rjust(16) for m in machines))
    for model in sorted(matrix, key=lambda m: -max((v for v, _ in matrix[m].values()), default=0)):
        row = "".join(
            (f"{matrix[model][mid][0]:.{digits}f}{'*' if matrix[model][mid][1] else ' '}"
             if mid in matrix[model] else "— ").rjust(16)
            for mid in machines)
        print(model[:width - 2].ljust(width) + row)
    if any(so for cells in matrix.values() for _v, so in cells.values()):
        print("\n* vitesse seule (bench_speed_only.py) : test complet non fait sur cette machine.")

    if args.csv:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["machine", "mode", "vram_gb", "ram_gb", "campagne", "modele",
                        *[label for _path, label, _digits in FIELDS], "vitesse_seule"])
            for run in runs:
                m = run["machine"]
                for campaign, key in CAMPAIGNS.items():
                    for model in run.get(key, {}):
                        cells = [value(run, campaign, model, path) for path, _label, _digits in FIELDS]
                        w.writerow([m["machine_id"], m["mode"], m["vram_gb"], m["ram_gb"], campaign, model,
                                    *["" if v is None else v for v, _so in cells],
                                    any(so for _v, so in cells)])
        print(f"\nCSV écrit : {CSV_PATH}")


if __name__ == "__main__":
    main()
