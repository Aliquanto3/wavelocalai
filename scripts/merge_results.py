#!/usr/bin/env python3
"""Fusionne les résultats de plusieurs machines et les compare.

    python scripts/merge_results.py                 # tableau comparatif
    python scripts/merge_results.py --csv           # écrit benchmarks/comparison.csv

Chaque machine publie son propre fichier dans benchmarks/results/ : un fichier
par machine, donc aucun conflit de fusion git. Le script refuse de comparer en
silence des mesures produites par des versions différentes du benchmark.
"""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
RESULTS_DIR = ROOT / "benchmarks" / "results"
CSV_PATH = ROOT / "benchmarks" / "comparison.csv"

FIELDS = [
    ("avg_tokens_per_second", "tok/s"),
    ("gpu_offload_pct", "% GPU"),
    ("model_memory_at_max_ctx_gb", "Go"),
    ("avg_ttft_ms", "TTFT ms"),
    ("max_validated_ctx", "ctx"),
]


def load_all() -> list[dict]:
    if not RESULTS_DIR.exists():
        raise SystemExit(f"Aucun résultat : {RESULTS_DIR} n'existe pas.")
    runs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS_DIR.glob("*.json"))]
    if not runs:
        raise SystemExit(f"Aucun fichier dans {RESULTS_DIR}.")
    return runs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", action="store_true", help="Écrire benchmarks/comparison.csv")
    ap.add_argument("--metric", default="avg_tokens_per_second",
                    help="Métrique comparée dans le tableau (défaut : avg_tokens_per_second)")
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
    matrix: dict[str, dict[str, float]] = defaultdict(dict)
    for run in runs:
        mid = run["machine"]["machine_id"]
        for model, stats in run["models"].items():
            value = stats.get(args.metric)
            if isinstance(value, (int, float)):
                matrix[model][mid] = value

    machines = [r["machine"]["machine_id"] for r in runs]
    width = max((len(m) for m in matrix), default=10) + 2
    print(f"\n{args.metric}\n")
    print("modèle".ljust(width) + "".join(m[:14].rjust(16) for m in machines))
    for model in sorted(matrix, key=lambda m: -max(matrix[m].values(), default=0)):
        row = "".join(
            (f"{matrix[model][mid]:.1f}" if mid in matrix[model] else "—").rjust(16)
            for mid in machines)
        print(model[:width - 2].ljust(width) + row)

    if args.csv:
        CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["machine", "mode", "vram_gb", "ram_gb", "modele",
                        *[label for _key, label in FIELDS]])
            for run in runs:
                m = run["machine"]
                for model, stats in run["models"].items():
                    w.writerow([m["machine_id"], m["mode"], m["vram_gb"], m["ram_gb"], model,
                                *[stats.get(key, "") for key, _label in FIELDS]])
        print(f"\nCSV écrit : {CSV_PATH}")


if __name__ == "__main__":
    main()
