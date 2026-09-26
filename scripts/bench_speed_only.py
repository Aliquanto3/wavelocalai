#!/usr/bin/env python3
"""Mesure la seule vitesse d'un modèle, palier de contexte par palier.

Pour les modèles trop lents sur une machine donnée, le test complet (outils,
langues, raisonnement, campagne « au mieux ») prendrait des heures pour un
résultat sans usage réaliste. On ne mesure alors que ce qui dépend du poste :
vitesse de génération et délai avant le premier token, en fonction du contexte.

La mesure elle-même est celle de benchmark_slm.py (benchmark_inference), qu'on
importe sans la modifier : son empreinte git, qui garantit la comparabilité
entre machines, reste inchangée.

    python scripts/bench_speed_only.py --models olmo-3:7b granite4.2:8b \\
        --reason "moins de 10 tok/s à 8K sur cette machine"

Les résultats vont dans data/models.json sous `benchmark_stats_speed_only` ;
`bench_here.py export` les publie à part, sous `models_speed_only`.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import benchmark_slm as bs  # noqa: E402

STATS_KEY = "benchmark_stats_speed_only"


def measure(tag: str, contexts: list[int], args: argparse.Namespace) -> dict[int, list[dict]]:
    """Mesures brutes par palier : {contexte: [résultat de chaque exécution]}."""
    by_ctx: dict[int, list[dict]] = {c: [] for c in contexts}
    # Préchauffe : le premier chargement lit le modèle sur disque, et une partie de
    # ce temps retombe dans le TTFT du premier palier (jusqu'à 20 s mesurées).
    # benchmark_slm.py y échappe car ses tests fonctionnels chargent le modèle avant.
    bs.ollama.generate(model=tag, prompt="Bonjour", options={"num_ctx": contexts[0], "num_predict": 1})
    bs.unload_model(tag)
    for run_id in range(1, args.runs + 1):
        bs.logger.info(f"   📍 Run {run_id}/{args.runs}")
        if args.cooldown_temp > 0:
            cd = bs.wait_for_cooldown(args.cooldown_temp, args.cooldown_max)
            if cd["waited_s"]:
                bs.logger.info(f"   ❄️  Refroidissement {cd['waited_s']:.0f}s : "
                               f"{cd['start_temp_c']:.0f}°C -> {cd['end_temp_c']:.0f}°C")
        for ctx in contexts:
            bench = bs.benchmark_inference(tag, ctx, "local", args.country, args.output_tokens,
                                           thinking=False, vendor_params=False)
            if not bench:
                bs.logger.warning(f"      ❌ Échec à ctx={ctx}, paliers suivants abandonnés")
                break
            by_ctx[ctx].append(bench)
            bs.logger.info(f"      ⚡ {ctx} : {bench['tokens_per_second']} tok/s | "
                           f"TTFT {bench['time_to_first_token_ms']}ms "
                           f"(prompt complet {bench['ttft_full_prompt_ms']}ms) | "
                           f"GPU {bench['gpu_offload_pct']}% {bench['gpu_clock_mhz']:.0f}MHz")
            if bench.get("swap_delta_gb", 0) > bs.SWAP_DELTA_THRESHOLD_GB:
                bs.logger.warning("      📉 SWAP disque détecté : paliers suivants abandonnés")
                break
    return by_ctx


def summarize(by_ctx: dict[int, list[dict]], args: argparse.Namespace) -> dict:
    per_ctx = {}
    for ctx, runs in by_ctx.items():
        if not runs:
            continue
        per_ctx[str(ctx)] = {
            "tokens_per_second": bs.dispersion([r["tokens_per_second"] for r in runs]),
            "time_to_first_token_ms": bs.dispersion([r["time_to_first_token_ms"] for r in runs], digits=0),
            "ttft_full_prompt_ms": bs.dispersion([r["ttft_full_prompt_ms"] for r in runs], digits=0),
            "prefill_tokens_per_second": bs.dispersion([r["prefill_tokens_per_second"] for r in runs], digits=1),
            "model_memory_gb": max(r["model_memory_gb"] for r in runs),
            "gpu_offload_pct": min(r["gpu_offload_pct"] for r in runs),
            "gpu_clock_mhz": bs.dispersion([r["gpu_clock_mhz"] for r in runs], digits=0),
        }
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "reason": args.reason,
        "protocol": {
            "runs": args.runs,
            "output_tokens": args.output_tokens,
            "temperature": 0.7,
            "thinking": False,
            "cooldown_temp_c": args.cooldown_temp,
        },
        "max_validated_ctx": max((int(c) for c in per_ctx), default=0),
        "by_context": per_ctx,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", "-m", nargs="+", required=True, help="Tags Ollama à mesurer")
    ap.add_argument("--reason", required=True, help="Pourquoi le test complet n'est pas fait")
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--max-context", type=int, default=16384)
    ap.add_argument("--output-tokens", type=int, default=bs.DEFAULT_OUTPUT_TOKENS)
    ap.add_argument("--cooldown-temp", type=float, default=bs.DEFAULT_COOLDOWN_TEMP_C)
    ap.add_argument("--cooldown-max", type=float, default=bs.DEFAULT_COOLDOWN_MAX_S)
    ap.add_argument("--country", default=bs.DEFAULT_COUNTRY_ISO_CODE)
    args = ap.parse_args()

    db_path = bs.MODELS_JSON_PATH
    names = {v.get("ollama_tag"): n for n, v in json.loads(db_path.read_text(encoding="utf-8")).items()}
    unknown = [t for t in args.models if t not in names]
    if unknown:
        sys.exit(f"Absents de {db_path} : {', '.join(unknown)}")

    for i, tag in enumerate(args.models, 1):
        name = names[tag]
        db = json.loads(db_path.read_text(encoding="utf-8"))
        max_ctx = min(args.max_context, db[name].get("ctx", 4096))
        contexts = [c for c in bs.CONTEXT_LEVELS if c <= max_ctx]
        bs.logger.info(f"\n[{i}/{len(args.models)}] 🔬 {name} — vitesse seule, contextes {contexts}")

        stats = summarize(measure(tag, contexts, args), args)
        bs.unload_model(tag)
        if not stats["by_context"]:
            bs.logger.warning(f"   Aucune mesure pour {name} : rien n'est enregistré")
            continue

        # Relecture juste avant l'écriture : un autre outil a pu modifier le fichier.
        db = json.loads(db_path.read_text(encoding="utf-8"))
        db[name][STATS_KEY] = stats
        db_path.write_text(json.dumps(db, ensure_ascii=False, indent=4), encoding="utf-8")
        bs.logger.info(f"   📝 {STATS_KEY} enregistré ({len(stats['by_context'])} paliers)")


if __name__ == "__main__":
    main()
