#!/usr/bin/env python3
"""Lance le benchmark SLM sur la machine courante, de bout en bout.

    python scripts/bench_here.py plan     --label ma-tour   # que tester ici ?
    python scripts/bench_here.py install  --label ma-tour   # récupérer les manquants
    python scripts/bench_here.py run      --label ma-tour   # benchmarker
    python scripts/bench_here.py export   --label ma-tour   # fichier partageable

Le choix des modèles part de l'empreinte mémoire réellement mesurée (catalogue),
pas de la taille du fichier : c'est elle qui décide du placement GPU, donc de la
vitesse.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.machine_profile import build as build_profile  # noqa: E402
from scripts.machine_profile import describe  # noqa: E402

CATALOG = ROOT / "config" / "models_catalog.json"
LOCAL_DB = ROOT / "data" / "models.json"
RESULTS_DIR = ROOT / "benchmarks" / "results"
GGUF_DIR = Path("D:/ia/gguf") if Path("D:/").exists() else ROOT / "data" / "gguf"

# Marge appliquée à l'empreinte de référence : une autre machine, un autre
# pilote et un autre contexte ne donnent pas exactement la même occupation.
FIT_MARGIN = 1.10
# Sans mesure disponible, on estime l'empreinte à partir du téléchargement.
SIZE_TO_LOADED = 1.25


def load_catalog() -> dict[str, Any]:
    if not CATALOG.exists():
        sys.exit(f"Catalogue introuvable : {CATALOG}\nLancez d'abord scripts/build_catalog.py")
    return json.loads(CATALOG.read_text(encoding="utf-8"))["models"]


def parse_size(value: Any) -> float:
    try:
        return float(str(value).replace("GB", "").replace("≈", "").strip())
    except (TypeError, ValueError):
        return 0.0


def estimated_load(entry: dict[str, Any]) -> float:
    measured = entry.get("measured_loaded_gb")
    return float(measured) if measured else parse_size(entry.get("size_gb")) * SIZE_TO_LOADED


def active_params(entry: dict[str, Any]) -> float:
    raw = entry.get("params_act") or entry.get("params_tot") or "0"
    try:
        return float(str(raw).rstrip("B"))
    except ValueError:
        return 0.0


def select(profile: dict[str, Any], catalog: dict[str, Any]) -> tuple[list, list]:
    """Retourne (retenus, écartés) — chaque élément est (nom, entrée, raison)."""
    budget = profile["budget_gb"]
    keep, drop = [], []

    for name, entry in catalog.items():
        if entry.get("type") != "local":
            drop.append((name, entry, "modèle API, hors périmètre"))
            continue

        load = estimated_load(entry)
        fits = load * FIT_MARGIN <= budget
        total = parse_size(entry.get("size_gb"))
        act = active_params(entry)
        if entry.get("moe"):
            # Un MoE ne tient pas en VRAM : Ollama place les experts en RAM et
            # n'y active qu'une fraction des poids. C'est donc la RAM qui décide
            # s'il passe, et les paramètres actifs qui donnent la vitesse.
            ram = profile["ram_gb"]
            if total <= ram * 0.6:
                keep.append((name, entry, f"MoE {act:.0f}B actifs, {total:.0f} Go en RAM"))
            elif total <= ram * 0.78:
                keep.append((name, entry, f"MoE {total:.0f} Go sur {ram:.0f} Go : tendu, fermez vos applications"))
            else:
                drop.append((name, entry, f"MoE de {total:.0f} Go : trop pour {ram:.0f} Go de RAM"))
            continue

        if profile["mode"] == "cpu":
            # Sans GPU, c'est la RAM qui accueille le modèle et ce sont les
            # paramètres actifs qui déterminent la vitesse.
            act = active_params(entry)
            if load > profile["ram_gb"] * 0.6:
                drop.append((name, entry, f"{load:.1f} Go, trop pour {profile['ram_gb']} Go de RAM"))
            elif act > 8:
                drop.append((name, entry, f"{act:.0f}B actifs : trop lent sans GPU"))
            else:
                keep.append((name, entry, f"{act:.1f}B actifs, {load:.1f} Go"))
            continue

        if fits:
            keep.append((name, entry, f"{load:.1f} Go tient dans {budget} Go"))
        elif load <= budget * 1.6:
            keep.append((name, entry, f"{load:.1f} Go : débordement CPU partiel attendu"))
        else:
            drop.append((name, entry, f"{load:.1f} Go dépasse largement {budget} Go"))

    keep.sort(key=lambda item: estimated_load(item[1]))
    return keep, drop


def installed_tags() -> set[str]:
    exe = shutil.which("ollama")
    if not exe:
        return set()
    out = subprocess.run([exe, "list"], capture_output=True, text=True, timeout=30).stdout
    tags = set()
    for line in out.splitlines()[1:]:
        if line.strip():
            tag = line.split()[0]
            tags.add(tag)
            tags.add(tag.removesuffix(":latest"))
    return tags


def cmd_plan(args: argparse.Namespace) -> None:
    profile = build_profile(args.label)
    catalog = load_catalog()
    keep, drop = select(profile, catalog)
    have = installed_tags()

    print(describe(profile))
    print("\n" + "=" * 72)
    print(f"{len(keep)} modèles pertinents pour cette machine\n")

    to_get = 0.0
    for name, entry, why in keep:
        tag = entry["ollama_tag"]
        status = "déjà installé" if tag in have else f"à télécharger ({parse_size(entry['size_gb'])} Go)"
        if tag not in have:
            to_get += parse_size(entry["size_gb"])
        print(f"  {name:34} {tag:32} {why:38} {status}")

    if args.verbose and drop:
        print(f"\n{len(drop)} modèles écartés :")
        for name, _entry, why in drop:
            print(f"  {name:34} {why}")

    print(f"\nÀ télécharger : {to_get:.1f} Go — disque libre : {profile['disk_free_gb']} Go")
    print(f"Étape suivante : python scripts/bench_here.py install --label {args.label or '<nom>'}")


def pull_via_hf(entry: dict[str, Any], tag: str) -> bool:
    """Repli pour les modèles absents de la bibliothèque Ollama."""
    fb = entry["hf_fallback"]
    GGUF_DIR.mkdir(parents=True, exist_ok=True)
    target = GGUF_DIR / fb["file"]

    hf = shutil.which("hf") or str(ROOT / ".venv" / "Scripts" / "hf.exe")
    print(f"    téléchargement Hugging Face : {fb['repo']}/{fb['file']}")
    if subprocess.run([hf, "download", fb["repo"], fb["file"],
                       "--local-dir", str(GGUF_DIR)]).returncode != 0:
        print("    échec du téléchargement")
        return False

    modelfile = GGUF_DIR / f"Modelfile.{tag.replace(':', '_').replace('/', '_')}"
    lines = [f"FROM {target.as_posix()}"]
    donor = fb.get("template_from")
    if fb.get("modelfile"):
        # Gabarit fourni par l'éditeur du modèle : il prime sur tout emprunt.
        lines.append(fb["modelfile"])
    elif donor:
        # On reprend le Modelfile complet du modèle officiel voisin : un TEMPLATE
        # multi-lignes tronqué produit une erreur "unexpected EOF" à l'import.
        out = subprocess.run(["ollama", "show", "--modelfile", donor],
                             capture_output=True, text=True).stdout
        lines += [ln for ln in out.splitlines()
                  if not ln.startswith("FROM ") and not ln.startswith("#")]
    modelfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return subprocess.run(["ollama", "create", tag, "-f", str(modelfile)]).returncode == 0


def cmd_install(args: argparse.Namespace) -> None:
    profile = build_profile(args.label)
    catalog = load_catalog()
    keep, _ = select(profile, catalog)
    have = installed_tags()

    missing = [(n, e) for n, e, _ in keep if e["ollama_tag"] not in have]
    if not missing:
        print("Tous les modèles retenus sont déjà installés.")
        return

    total = sum(parse_size(e["size_gb"]) for _, e in missing)
    print(f"{len(missing)} modèles à installer, {total:.1f} Go au total :")
    for name, entry in missing:
        print(f"  {name:34} {entry['ollama_tag']:32} {parse_size(entry['size_gb']):5.2f} Go")

    if not args.yes:
        if input("\nLancer les téléchargements ? [o/N] ").strip().lower() not in ("o", "oui", "y"):
            print("Abandon.")
            return

    for name, entry in missing:
        tag = entry["ollama_tag"]
        print(f"\n-> {name} ({tag})")
        if "hf_fallback" in entry:
            ok = pull_via_hf(entry, tag)
        else:
            ok = subprocess.run(["ollama", "pull", tag]).returncode == 0
        print("   " + ("installé" if ok else "ÉCHEC — modèle ignoré pour le benchmark"))


def cmd_run(args: argparse.Namespace) -> None:
    profile = build_profile(args.label)
    catalog = load_catalog()
    keep, _ = select(profile, catalog)
    have = installed_tags()
    tags = [e["ollama_tag"] for _, e, _ in keep if e["ollama_tag"] in have]
    if not tags:
        sys.exit("Aucun modèle installé parmi ceux retenus : lancez d'abord la commande install.")

    # data/models.json est la copie de travail du script de benchmark : on la
    # sème depuis le catalogue si elle n'existe pas encore sur cette machine.
    if not LOCAL_DB.exists():
        LOCAL_DB.parent.mkdir(parents=True, exist_ok=True)
        LOCAL_DB.write_text(json.dumps(catalog, ensure_ascii=False, indent=4), encoding="utf-8")
        print(f"Copie de travail créée : {LOCAL_DB}")

    # Sans GPU, on réduit le contexte et la génération : sinon un run dure la nuit.
    max_ctx = args.max_context or (8192 if profile["mode"] == "cpu" else 16384)
    cmd = [sys.executable, str(ROOT / "scripts" / "benchmark_slm.py"),
           "--max-context", str(max_ctx), "--force-tool-test", "--models", *tags]
    if profile["mode"] == "cpu":
        cmd += ["--output-tokens", "128"]

    print(f"Mode {profile['mode']} — {len(tags)} modèles, contexte jusqu'à {max_ctx}")
    print(" ".join(cmd) + "\n")
    subprocess.run(cmd, check=False)


def cmd_export(args: argparse.Namespace) -> None:
    profile = build_profile(args.label)
    if not LOCAL_DB.exists():
        sys.exit("Aucun résultat local : lancez d'abord la commande run.")

    db = json.loads(LOCAL_DB.read_text(encoding="utf-8"))
    results = {n: v["benchmark_stats"] for n, v in db.items() if v.get("benchmark_stats")}
    if not results:
        sys.exit("data/models.json ne contient aucun benchmark_stats.")

    sha = subprocess.run(["git", "log", "-1", "--format=%H", "--", "scripts/benchmark_slm.py"],
                         capture_output=True, text=True, cwd=ROOT).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "scripts/benchmark_slm.py"],
                           capture_output=True, text=True, cwd=ROOT).stdout.strip()

    payload = {
        "machine": profile,
        "benchmark_commit": sha or "inconnu",
        "benchmark_dirty": bool(dirty),  # code modifié localement : comparaison à prendre avec réserve
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "models": results,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = RESULTS_DIR / f"{profile['machine_id']}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(results)} modèles exportés -> {out}")
    if dirty:
        print("⚠️  scripts/benchmark_slm.py est modifié localement : commitez avant de comparer.")
    branch = f"bench/{profile['machine_id']}"
    print("\nPour partager ces résultats :")
    print(f"  git checkout -b {branch}")
    print(f"  git add {out.relative_to(ROOT).as_posix()} && git commit -m 'Bench: {profile['machine_id']}'")
    print(f"  git push -u origin {branch} && gh pr create --fill")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan", "install", "run", "export"])
    ap.add_argument("--label", help="Nom lisible de la machine (ex: tour-rtx4090)")
    ap.add_argument("--max-context", type=int, help="Forcer le contexte maximal testé")
    ap.add_argument("--yes", "-y", action="store_true", help="Ne pas demander confirmation")
    ap.add_argument("--verbose", "-v", action="store_true", help="Afficher aussi les modèles écartés")
    args = ap.parse_args()

    {"plan": cmd_plan, "install": cmd_install, "run": cmd_run, "export": cmd_export}[args.command](args)


if __name__ == "__main__":
    main()
