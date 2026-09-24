#!/usr/bin/env python3
"""Recalcule les statistiques de data/models.json à partir des lignes brutes du CSV.

Quand seule l'agrégation change, remesurer est inutile : chaque palier de chaque
exécution est déjà dans data/benchmarks_data.csv. Le CSV ne dit pas à quelle
campagne appartient une ligne ; on la désigne par sa fenêtre horaire.

    python scripts/reaggregate_benchmark.py --since "2026-09-24 08:47" --until "2026-09-24 10:50"
    python scripts/reaggregate_benchmark.py --since "2026-09-24 10:50" --stats-key benchmark_stats_vendor
"""

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import benchmark_slm as bench  # noqa: E402


def parse_value(value: str):
    """Rend au CSV les types que run_full_benchmark avait produits."""
    if value in ("True", "False"):
        return value == "True"
    for cast in (int, float):
        try:
            return cast(value)
        except ValueError:
            pass
    return value  # texte, y compris reasoning_by_category (JSON attendu en chaîne)


def load_rows(since: str, until: str, models: list[str] | None) -> dict[str, list[dict]]:
    by_model: dict[str, list[dict]] = {}
    with open(bench.DATASET_CSV_PATH, newline="", encoding="utf-8") as f:
        for raw in csv.DictReader(f):
            if not since <= raw["date"] <= until:
                continue
            if models and raw["ollama_tag"] not in models:
                continue
            # Champs vides omis : update_model_json leur applique ses valeurs par défaut.
            row = {k: parse_value(v) for k, v in raw.items() if v != ""}
            by_model.setdefault(raw["model_name"], []).append(row)
    return by_model


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", required=True, help="Début de la campagne (AAAA-MM-JJ HH:MM)")
    ap.add_argument("--until", default="9999", help="Fin de la campagne (défaut : aucune)")
    ap.add_argument("--stats-key", default="benchmark_stats",
                    help="Clé à réécrire (benchmark_stats ou benchmark_stats_vendor)")
    ap.add_argument("--models", nargs="+", help="Limiter à ces tags Ollama")
    ap.add_argument("--dry-run", action="store_true", help="Afficher sans écrire")
    args = ap.parse_args()

    db = json.loads(bench.MODELS_JSON_PATH.read_text(encoding="utf-8"))
    by_model = load_rows(args.since, args.until, args.models)
    if not by_model:
        sys.exit("Aucune ligne du CSV dans cette fenêtre.")

    for name, rows in by_model.items():
        if name not in db:
            print(f"  ? {name} : absent de models.json, ignoré")
            continue
        before = dict(db[name].get(args.stats_key) or {})
        bench.update_model_json(db, name, rows, args.stats_key)
        after = db[name][args.stats_key]
        if before.get("date"):
            # La date reste celle de la mesure, pas celle du recalcul.
            after["date"] = before["date"]
        tps = after["runs"].get("tokens_per_second", {})
        print(f"  {name:34} ctx {before.get('max_validated_ctx', '-'):>5} -> {after['max_validated_ctx']:>5}"
              f" | tok/s {before.get('avg_tokens_per_second', '-'):>7} -> {after['avg_tokens_per_second']:>7}"
              f" | runs n={tps.get('n', 0)}")

    if args.dry_run:
        print("\n(dry-run : rien n'est écrit)")
        return
    shutil.copy(bench.MODELS_JSON_PATH, str(bench.MODELS_JSON_PATH) + ".bak")
    bench.MODELS_JSON_PATH.write_text(json.dumps(db, indent=4, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(by_model)} modèle(s) réagrégé(s) sous {args.stats_key} -> {bench.MODELS_JSON_PATH}")


if __name__ == "__main__":
    main()
