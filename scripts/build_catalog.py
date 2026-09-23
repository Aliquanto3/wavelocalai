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
    # Gabarit publié par OpenBMB (docs/deployment/ollama.md) : aucun modèle
    # officiel voisin ne convient, MiniCPM5 n'étant pas dans la bibliothèque.
    "minicpm5:2b-q4_k_m": {
        "repo": "openbmb/MiniCPM5-2B-GGUF",
        "file": "MiniCPM5-2B-Q4_K_M.gguf",
        "modelfile": (
            'TEMPLATE """{{- if .Messages -}}\n'
            "{{- range .Messages -}}\n"
            "<|im_start|>{{ .Role }}\n"
            "{{ .Content }}<|im_end|>\n"
            "{{ end -}}\n"
            "<|im_start|>assistant\n"
            '{{ end -}}"""\n'
            'PARAMETER stop "<|im_end|>"\n'
            'PARAMETER stop "</s>"\n'
            "PARAMETER temperature 1.0\n"
            "PARAMETER top_p 0.95"
        ),
    },
}

# Machine ayant fourni les empreintes de référence.
REFERENCE = "RTX 3060 Laptop 6 Go VRAM / 32 Go RAM / Ollama 0.34.2"

# Modèles repérés comme intéressants mais qu'Ollama ne sait pas encore charger.
# Ils restent dans le catalogue pour ne pas être réévalués à chaque veille, et
# sont écartés de la sélection tant que le verrou n'a pas sauté.
PENDING = {
    "K2 Horizon 3.7B": {
        "ollama_tag": "k2-horizon:3.7b-q4_k_m",
        "type": "local",
        "editor": "Institute of Foundation Models",
        "size_gb": "3.16 GB",
        "params_tot": "3.7B",
        "params_act": "3.7B",
        "ctx": 524288,
        "capabilities": ["chat", "tools", "thinking"],
        "role": "assistant_light",
        "desc": (
            "Dense 3,7B à raisonnement étendu (sept. 2026), Apache 2.0, 524K de contexte. "
            "En tête des modèles ouverts sous 4B sur l'indice Artificial Analysis. "
            "Paramètres recommandés : temperature 1.0, top_p 0.95, et au moins 32 768 "
            "tokens de sortie — notre protocole standardisé le sous-évaluerait."
        ),
        "status": "pending",
        "blocked_by": (
            "L'architecture k2_horizon n'est pas supportée par llama.cpp en amont, "
            "dont dépend Ollama depuis la version 0.30. Seul le fork de l'éditeur "
            "sait la charger."
        ),
        "tracking": "https://github.com/ggml-org/llama.cpp/issues/28361",
        "checked_on": "2026-09-23",
        "hf_fallback": {
            "repo": "IFM/K2-Horizon-3.7B-GGUF",
            "file": "K2-Horizon-4B-Q4_K_M.gguf",
            "template_from": None,
        },
    },
}


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

    catalog["models"].update(PENDING)

    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    # Saut de ligne final : sans lui, le hook end-of-file-fixer le rajoute à
    # chaque commit et le fichier oscille d'une régénération à l'autre.
    CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    measured = sum(1 for m in catalog["models"].values() if "measured_loaded_gb" in m)
    print(f"{len(catalog['models'])} modèles ({measured} avec empreinte mesurée) -> {CATALOG}")


if __name__ == "__main__":
    main()
