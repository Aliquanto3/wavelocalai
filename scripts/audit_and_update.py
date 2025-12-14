import argparse
import contextlib
import csv
import json
import logging
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import psutil

# Ajout du path pour les imports internes
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

try:
    import ollama
    from codecarbon import OfflineEmissionsTracker

    from src.core.config import DATA_DIR, LOGS_DIR
except ImportError as e:
    print(f"❌ Erreur d'import : {e}")
    sys.exit(1)

# --- CONFIGURATION ---
MODELS_JSON_PATH = DATA_DIR / "models.json"
REPORT_MD_PATH = DATA_DIR / "benchmark_report.md"
DATASET_CSV_PATH = DATA_DIR / "benchmarks_data.csv"
AUDIT_LOG_FILE = LOGS_DIR / f"audit_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

MIN_RAM_MARGIN_GB = 1.0
CONTEXT_LEVELS = [2048, 8192, 16384, 32768, 65536]
TOTAL_RAM_GB = round(psutil.virtual_memory().total / (1024**3), 2)

# Configuration Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(AUDIT_LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# --- GESTION CSV (NOUVEAU : MODE APPEND) ---


def initialize_csv():
    """Crée le fichier CSV avec les headers s'il n'existe pas."""
    if not DATASET_CSV_PATH.exists():
        headers = [
            "model_name",
            "ollama_tag",
            "disk_size_gb",
            "context_size",
            "input_tokens",
            "output_tokens",
            "ollama_ram_usage_gb",
            "ram_peak_gb",
            "ram_delta_gb",
            "co2_kg",
            "duration_s",
            "status",
            "date",
        ]
        with open(DATASET_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)


def append_to_csv(model_name, ollama_tag, size_gb, benchmarks):
    """Ajoute une liste de résultats à la fin du CSV existant."""
    if not benchmarks:
        return

    with open(DATASET_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for bench in benchmarks:
            # Nettoyage de la taille (ex: "1.5 GB" -> "1.5")
            clean_size = size_gb.replace(" GB", "") if size_gb else "0"

            row = [
                model_name,
                ollama_tag,
                clean_size,
                bench.get("context_size"),
                bench.get("input_tokens", 0),
                bench.get("output_tokens", 0),
                bench.get("ollama_ram_usage_gb", 0),
                bench.get("ram_peak_gb", 0),
                0,  # ram_delta_gb (Legacy, on met 0)
                f"{bench.get('co2_kg'):.8f}",
                bench.get("speed_s"),
                bench.get("status"),
                bench.get("date", datetime.now().strftime("%Y-%m-%d")),
            ]
            writer.writerow(row)


# --- OUTILS DE MAINTENANCE ---


def unload_model(model_tag):
    try:
        ollama.chat(model=model_tag, messages=[], keep_alive=0)
        time.sleep(2)
    except Exception:
        pass


def get_system_ram_stats():
    mem = psutil.virtual_memory()
    return mem.used / (1024**3), mem.available / (1024**3)


def get_ollama_process_memory_gb():
    total_mem_bytes = 0
    try:
        for proc in psutil.process_iter(["name", "memory_info"]):
            try:
                if "ollama" in proc.info["name"].lower():
                    total_mem_bytes += proc.info["memory_info"].rss
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
    except Exception:
        pass
    return total_mem_bytes / (1024**3)


# --- TESTS TECHNIQUES ---


def test_tool_capabilities(model_tag):
    test_tool = {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"],
            },
        },
    }
    messages = [{"role": "user", "content": "What is the weather in Paris?"}]
    try:
        resp = ollama.chat(
            model=model_tag,
            messages=messages,
            tools=[test_tool],
            options={"temperature": 0, "num_ctx": 2048},
        )
        return bool(resp.message.tool_calls)
    except Exception:
        return False


def test_language_support(model_tag, lang_code):
    lang_map = {"fr": "French", "es": "Spanish", "de": "German", "it": "Italian", "zh": "Chinese"}
    target = lang_map.get(lang_code, lang_code)
    msg = [
        {
            "role": "user",
            "content": f"Translate the word 'Hello' into {target}. Return only the translated word.",
        }
    ]
    try:
        resp = ollama.chat(
            model=model_tag, messages=msg, options={"temperature": 0, "num_ctx": 2048}
        )
        return len(resp.message.content.strip()) > 0
    except Exception:
        return False


def benchmark_single_pass(model_tag, context_window, output_token_limit=512):
    unload_model(model_tag)

    _, sys_ram_avail = get_system_ram_stats()
    if sys_ram_avail < MIN_RAM_MARGIN_GB:
        logger.warning(f"   ⚠️  RAM Système insuffisante ({sys_ram_avail:.2f}GB dispo).")
        return None

    ollama_ram_start = get_ollama_process_memory_gb()

    tracker = OfflineEmissionsTracker(
        country_iso_code="FRA", output_dir=str(LOGS_DIR), log_level="error"
    )
    tracker.start()
    start_time = time.perf_counter()

    messages = [
        {
            "role": "user",
            "content": "Write a very detailed technical guide about space travel physics.",
        }
    ]

    try:
        resp = ollama.chat(
            model=model_tag,
            messages=messages,
            options={
                "num_ctx": context_window,
                "temperature": 0.7,
                "num_predict": output_token_limit,
                "repeat_penalty": 1.1,
                "stop": ["<|endoftext|>", "User:", "Assistant:"],
            },
        )

        duration = time.perf_counter() - start_time

        ollama_ram_end = get_ollama_process_memory_gb()
        sys_ram_peak, _ = get_system_ram_stats()
        emissions = tracker.stop()

        ram_model_usage = max(0, ollama_ram_end - ollama_ram_start)

        input_tokens = getattr(resp, "prompt_eval_count", 0) or 0
        output_tokens = getattr(resp, "eval_count", 0) or 0
        if output_tokens == 0:
            output_tokens = len(resp.message.content.split())

        status = "OK"
        if output_tokens >= output_token_limit * 0.9:
            status = "MAX_TOKENS_HIT"

        unload_model(model_tag)

        return {
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "context_size": context_window,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "ollama_ram_usage_gb": round(ram_model_usage, 3),
            "ram_peak_gb": round(sys_ram_peak, 2),
            "co2_kg": float(emissions),
            "speed_s": round(duration, 2),
            "status": status,
        }

    except Exception as e:
        with contextlib.suppress(Exception):
            tracker.stop()
        logger.error(f"   ❌ Crash à ctx={context_window}: {e}")
        return None


def get_real_disk_size(model_tag):
    try:
        list_info = ollama.list()
        for m in list_info["models"]:
            if m["model"] == model_tag or m["model"] == f"{model_tag}:latest":
                return round(m["size"] / (1024**3), 2)
        return 0.0
    except Exception:
        return 0.0


def generate_markdown_report(db):
    """Génère le rapport MD en se basant sur les stats résumées."""
    logger.info(f"📝 Génération du rapport MD : {REPORT_MD_PATH}")

    headers = ["Modèle", "Tag", "Taille Disque", "Max Valid Context", "Max RAM Modèle", "Vitesse"]
    rows = []

    for name, data in db.items():
        tag = data.get("ollama_tag", "?")
        size = data.get("size_gb", "?")
        # On lit directement les stats résumées du JSON, car les détails ne sont plus là
        stats = data.get("benchmark_stats", {})

        if stats:
            max_ctx = str(stats.get("tested_ctx", "N/A"))
            ram = f"{stats.get('ram_usage_gb', 0)} GB"
            speed = f"{stats.get('speed_s', 0)} s"
        else:
            max_ctx = "N/A"
            ram = "N/A"
            speed = "N/A"

        rows.append([name, tag, size, max_ctx, ram, speed])

    with open(REPORT_MD_PATH, "w", encoding="utf-8") as f:
        f.write("# 📊 WaveLocalAI - Rapport de Stress Test\n")
        f.write(f"*Généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}*\n")
        f.write(f"**RAM Totale Installée : {TOTAL_RAM_GB} GB**\n\n")
        f.write(
            "> **Note :** Ce rapport affiche les performances maximales validées (sans swap). L'historique détaillé est dans `benchmarks_data.csv`.\n\n"
        )
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        for row in rows:
            f.write("| " + " | ".join(map(str, row)) + " |\n")


# --- MAIN LOOP ---


def main():
    parser = argparse.ArgumentParser(description="Audit et Stress Test des modèles")
    parser.add_argument(
        "--skip-tested", action="store_true", help="Ignorer les modèles déjà testés"
    )
    args = parser.parse_args()

    if not MODELS_JSON_PATH.exists():
        logger.error("Fichier models.json introuvable.")
        sys.exit(1)

    with open(MODELS_JSON_PATH, encoding="utf-8") as f:
        db = json.load(f)

    shutil.copy(MODELS_JSON_PATH, str(MODELS_JSON_PATH) + ".bak")

    try:
        installed = {m["model"]: m for m in ollama.list()["models"]}
    except Exception:
        logger.error("Ollama non détecté.")
        sys.exit(1)

    # Initialisation du CSV (Headers uniquement si fichier absent)
    initialize_csv()

    items = list(db.items())
    total = len(items)
    logger.info(f"🖥️  RAM TOTALE SYSTÈME : {TOTAL_RAM_GB} GB")

    for i, (name, data) in enumerate(items, 1):
        try:
            # On vérifie si benchmark_stats existe pour le skip
            if args.skip_tested and data.get("benchmark_stats"):
                logger.info(f"[{i}/{total}] ⏭️ {name} : Déjà testé.")
                continue

            tag = data.get("ollama_tag")
            real_tag = (
                tag
                if tag in installed
                else (f"{tag}:latest" if f"{tag}:latest" in installed else None)
            )

            if not real_tag:
                logger.warning(f"[{i}/{total}] ⏩ {name} : Non installé.")
                continue

            logger.info(f"\n🔎 [{i}/{total}] STRESS TEST : {name} ({real_tag})")

            size = get_real_disk_size(real_tag)
            if size:
                data["size_gb"] = f"{size} GB"

            if test_tool_capabilities(real_tag):
                if "tools" not in data.get("capabilities", []):
                    data.setdefault("capabilities", []).append("tools")
            else:
                if "tools" in data.get("capabilities", []):
                    data["capabilities"].remove("tools")

            bench_results = []
            max_model_ctx = data.get("ctx", 4096)
            prev_ram_usage = 0.0

            for ctx in CONTEXT_LEVELS:
                if ctx > max_model_ctx:
                    logger.info(f"   ⏹️  Limite théorique atteinte ({max_model_ctx}).")
                    break

                logger.info(f"   ⚡ Test contexte : {ctx} ...")
                res = benchmark_single_pass(real_tag, ctx)

                if res:
                    current_ram = res["ollama_ram_usage_gb"]

                    # LOGIQUE ANTI-SWAP
                    if prev_ram_usage > 0 and current_ram < prev_ram_usage:
                        logger.warning(
                            f"      📉 SWAP DETECTÉ. Arrêt. Max Validé : {bench_results[-1]['context_size']}"
                        )
                        break

                    bench_results.append(res)
                    prev_ram_usage = current_ram

                    # Logs
                    msg = f"      ✅ OK (RAM Modèle: {current_ram}GB | Peak: {res['ram_peak_gb']}/{TOTAL_RAM_GB} GB)"
                    if res["status"] == "MAX_TOKENS_HIT":
                        logger.info(f"{msg} - ⚠️ Bavard")
                    else:
                        logger.info(msg)
                else:
                    logger.warning(f"      ❌ Echec ou RAM insuffisante à {ctx}.")
                    break

            # --- MODIFICATION CRITIQUE ---
            # 1. On écrit immédiatement dans le CSV (mode append)
            append_to_csv(name, tag, data.get("size_gb"), bench_results)

            # 2. On met à jour SEULEMENT le résumé dans le JSON
            # (On ne stocke plus bench_results dans 'context_benchmarks')
            if bench_results:
                best = bench_results[-1]
                data["benchmark_stats"] = {
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "tested_ctx": best["context_size"],
                    "ram_usage_gb": best["ollama_ram_usage_gb"],
                    "co2_emissions_kg": sum(r["co2_kg"] for r in bench_results),
                    "speed_s": best["speed_s"],
                }

            # 3. On sauvegarde le JSON allégé
            with open(MODELS_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(db, f, indent=4, ensure_ascii=False)

        except KeyboardInterrupt:
            logger.warning("Arrêt d'urgence.")
            sys.exit(0)
        except Exception as e:
            logger.error(f"Erreur sur {name}: {e}")
            continue

    generate_markdown_report(db)
    logger.info(f"✅ Terminé ! Rapport : {REPORT_MD_PATH}")


if __name__ == "__main__":
    main()
