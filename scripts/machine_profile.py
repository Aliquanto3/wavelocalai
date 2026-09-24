#!/usr/bin/env python3
"""Profil matériel d'une machine et budget mémoire pour l'inférence locale.

Utilisé par bench_here.py pour choisir les modèles à tester, et embarqué dans le
fichier de résultats pour que deux machines restent comparables.

Usage : python scripts/machine_profile.py [--label ma-tour]
"""

import argparse
import hashlib
import json
import platform
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).parent.parent
PROFILE_PATH = ROOT / "data" / "machine_profile.json"

# Marge laissée au bureau, au cache de contexte et à la fragmentation.
VRAM_USABLE_RATIO = 0.85
# Sans GPU, on ne prend qu'une part de la RAM : le reste sert au système.
RAM_USABLE_RATIO = 0.5
RAM_BUDGET_CAP_GB = 16.0
# En dessous, un GPU n'apporte rien : on bascule en mode CPU.
MIN_USEFUL_VRAM_GB = 3.5


def _run(cmd: list[str]) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def detect_gpus() -> list[dict[str, Any]]:
    """GPU et VRAM, via nvidia-smi, rocm-smi, puis WMI en dernier recours."""
    gpus: list[dict[str, Any]] = []

    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    for line in (ln for ln in out.splitlines() if ln.strip()):
        name, _, mib = line.partition(",")
        try:
            gpus.append({"name": name.strip(), "vram_gb": round(int(mib) / 1024, 2), "vendor": "nvidia"})
        except ValueError:
            continue
    if gpus:
        return gpus

    out = _run(["rocm-smi", "--showmeminfo", "vram", "--json"])
    if out:
        try:
            for card, info in json.loads(out).items():
                total = next((v for k, v in info.items() if "total" in k.lower()), None)
                if total:
                    gpus.append({"name": f"AMD {card}", "vram_gb": round(int(total) / 1024**3, 2),
                                 "vendor": "amd"})
        except Exception:
            pass
    if gpus:
        return gpus

    if platform.system() == "Windows":
        out = _run(["powershell", "-NoProfile", "-Command",
                    "Get-CimInstance Win32_VideoController | "
                    "Select-Object Name,AdapterRAM | ConvertTo-Json -Compress"])
        try:
            data = json.loads(out) if out else []
            for card in (data if isinstance(data, list) else [data]):
                ram = card.get("AdapterRAM") or 0
                # AdapterRAM est tronqué à 4 Go et absent des GPU récents :
                # la valeur est indicative, pas fiable pour dimensionner.
                gpus.append({"name": card.get("Name", "?"), "vram_gb": round(ram / 1024**3, 2),
                             "vendor": "unknown", "vram_unreliable": True})
        except Exception:
            pass
    return gpus


def ollama_version() -> str | None:
    exe = shutil.which("ollama")
    if not exe:
        return None
    return (_run([exe, "--version"]) or "").replace("ollama version is", "").strip() or None


def machine_id(label: str | None) -> str:
    """Identifiant stable et non nominatif : hash du matériel, pas du nom d'utilisateur."""
    seed = f"{socket.gethostname()}|{platform.machine()}|{platform.processor()}"
    digest = hashlib.sha256(seed.encode()).hexdigest()[:8]
    return f"{label}-{digest}" if label else digest


def build(label: str | None = None) -> dict[str, Any]:
    gpus = detect_gpus()
    best = max(gpus, key=lambda g: g["vram_gb"], default=None)
    vram = best["vram_gb"] if best else 0.0
    ram_gb = round(psutil.virtual_memory().total / 1024**3, 1)

    gpu_mode = bool(best) and vram >= MIN_USEFUL_VRAM_GB and not best.get("vram_unreliable")
    if gpu_mode:
        budget = round(vram * VRAM_USABLE_RATIO, 2)
    else:
        budget = round(min(ram_gb * RAM_USABLE_RATIO, RAM_BUDGET_CAP_GB), 2)

    return {
        "machine_id": machine_id(label),
        "label": label,
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores_physical": psutil.cpu_count(logical=False),
        "cpu_cores_logical": psutil.cpu_count(logical=True),
        "ram_gb": ram_gb,
        "gpus": gpus,
        "vram_gb": vram,
        "mode": "gpu" if gpu_mode else "cpu",
        "budget_gb": budget,
        "disk_free_gb": round(psutil.disk_usage(str(ROOT)).free / 1024**3, 1),
        "ollama_version": ollama_version(),
        "python": platform.python_version(),
    }


def describe(p: dict[str, Any]) -> str:
    gpu = p["gpus"][0]["name"] if p["gpus"] else "aucun GPU détecté"
    lines = [
        f"Machine       : {p['machine_id']}",
        f"OS            : {p['os']}",
        f"CPU           : {p['cpu']} ({p['cpu_cores_physical']} cœurs physiques)",
        f"RAM           : {p['ram_gb']} Go",
        f"GPU           : {gpu}" + (f" — {p['vram_gb']} Go de VRAM" if p["vram_gb"] else ""),
        f"Ollama        : {p['ollama_version'] or 'non installé'}",
        f"Disque libre  : {p['disk_free_gb']} Go",
        "",
        f"Mode retenu   : {'GPU' if p['mode'] == 'gpu' else 'CPU seul'}",
        f"Budget modèle : {p['budget_gb']} Go",
    ]
    if p["mode"] == "cpu":
        lines.append("")
        lines.append("Sans GPU utilisable, la bande passante RAM devient le facteur limitant :")
        lines.append("privilégier les modèles à peu de paramètres actifs (MoE) ou ≤ 4B.")
    if p["gpus"] and p["gpus"][0].get("vram_unreliable"):
        lines.append("")
        lines.append("⚠️  VRAM non fiable (relevé WMI) : installez les pilotes NVIDIA/AMD")
        lines.append("    ou passez --vram-gb pour forcer la valeur.")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Profil matériel pour le benchmark SLM")
    ap.add_argument("--label", help="Nom lisible de la machine (ex: tour-rtx4090)")
    ap.add_argument("--vram-gb", type=float, help="Forcer la VRAM détectée (Go)")
    ap.add_argument("--json", action="store_true", help="Sortie JSON brute")
    args = ap.parse_args()

    profile = build(args.label)
    if args.vram_gb:
        profile["vram_gb"] = args.vram_gb
        profile["mode"] = "gpu" if args.vram_gb >= MIN_USEFUL_VRAM_GB else "cpu"
        profile["budget_gb"] = (round(args.vram_gb * VRAM_USABLE_RATIO, 2) if profile["mode"] == "gpu"
                                else profile["budget_gb"])

    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(profile, ensure_ascii=False, indent=2) if args.json else describe(profile))
    if not args.json:
        print(f"\nProfil enregistré : {PROFILE_PATH}")


if __name__ == "__main__":
    main()
