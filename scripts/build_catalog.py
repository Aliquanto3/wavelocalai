#!/usr/bin/env python3
"""Génère config/models_catalog.json (suivi par git) depuis data/models.json (local).

Le catalogue ne contient que les métadonnées partageables entre machines : tag,
éditeur, taille de téléchargement, capacités, et — quand la mesure existe —
l'empreinte réellement observée. C'est cette empreinte, et non la taille du
fichier, qui prédit si un modèle tiendra en VRAM.
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOCAL_DB = ROOT / "data" / "models.json"
CATALOG = ROOT / "config" / "models_catalog.json"

KEEP = ("ollama_tag", "type", "editor", "size_gb", "params_tot", "params_act",
        "ctx", "capabilities", "role", "desc")

# Modèles absents de la bibliothèque Ollama : Ollama 0.34 refuse la redirection
# du CDN Hugging Face ("blocked redirect to a different host"). On télécharge
# donc le GGUF puis on l'importe avec le gabarit d'un modèle officiel voisin.
HF_FALLBACK = {
    "bonsai:8b-q1_0": {
        "repo": "prism-ml/Bonsai-8B-gguf",
        "file": "Bonsai-8B-Q1_0.gguf",
        "template_from": None,  # gabarit détecté automatiquement
    },
    "bonsai:27b-q1_0": {
        "repo": "prism-ml/Bonsai-27B-gguf",
        "file": "Bonsai-27B-Q1_0.gguf",
        "template_from": "qwen3.5:4b",
    },
    "qwen3.5-ud:9b-q3_k_xl": {
        "repo": "unsloth/Qwen3.5-9B-GGUF",
        "file": "Qwen3.5-9B-UD-Q3_K_XL.gguf",
        "template_from": "qwen3.5:4b",
    },
    "gemma4-ud:12b-iq3_xxs": {
        "repo": "unsloth/gemma-4-12b-it-GGUF",
        "file": "gemma-4-12b-it-UD-IQ3_XXS.gguf",
        "template_from": "gemma4:e2b-it-qat",
    },
    "ministral3-ud:14b-iq2_m": {
        "repo": "unsloth/Ministral-3-14B-Instruct-2512-GGUF",
        "file": "Ministral-3-14B-Instruct-2512-UD-IQ2_M.gguf",
        "template_from": "ministral-3:3b",
    },
}

# Machine ayant fourni les empreintes de référence.
REFERENCE = "RTX 3060 Laptop 6 Go VRAM / 32 Go RAM / Ollama 0.34.2"


def main() -> None:
    db = json.loads(LOCAL_DB.read_text(encoding="utf-8"))
    catalog = {"_reference_machine": REFERENCE, "models": {}}

    for name, info in db.items():
        entry = {k: info[k] for k in KEEP if k in info}
        stats = info.get("benchmark_stats") or {}
        measured = stats.get("model_memory_at_max_ctx_gb")
        is_moe = "a3b" in info["ollama_tag"].lower() or "moe" in name.lower()
        if is_moe:
            # Pour un MoE, l'empreinte VRAM ne dimensionne rien : les experts
            # vivent en RAM. On s'en tient à la taille totale.
            measured = None
        if measured:
            # Empreinte observée au contexte maximal validé, machine de référence.
            entry["measured_loaded_gb"] = measured
            entry["measured_at_ctx"] = stats.get("max_validated_ctx")
        if info["ollama_tag"] in HF_FALLBACK:
            entry["hf_fallback"] = HF_FALLBACK[info["ollama_tag"]]
        # Vrai Mixture-of-Experts : les experts vivent en RAM et seule une
        # fraction des poids est active. À ne pas confondre avec les Per-Layer
        # Embeddings de Gemma 4, qui réduisent aussi les "paramètres actifs"
        # mais restent un modèle dense.
        entry["moe"] = is_moe
        catalog["models"][name] = entry

    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    measured = sum(1 for m in catalog["models"].values() if "measured_loaded_gb" in m)
    print(f"{len(catalog['models'])} modèles ({measured} avec empreinte mesurée) -> {CATALOG}")


if __name__ == "__main__":
    main()
