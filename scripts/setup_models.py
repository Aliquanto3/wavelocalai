import sys
import os
import argparse
import json
from pathlib import Path

# --- Ajout du chemin src au path ---
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

try:
    import ollama
    from tqdm import tqdm
    # On importe DATA_DIR pour localiser le JSON
    from src.core.config import DATA_DIR
except ImportError as e:
    print(f"❌ Erreur d'import : {e}")
    print("Assurez-vous d'avoir installé les dépendances (pip install tqdm) et d'être à la racine.")
    sys.exit(1)

MODELS_JSON_PATH = DATA_DIR / "models.json"

def check_ollama_connection():
    """Vérifie si Ollama est vivant"""
    try:
        ollama.list()
        return True
    except Exception:
        return False

def get_installed_tags():
    """Récupère l'ensemble des tags déjà installés"""
    try:
        models = ollama.list().get('models', [])
        return {m['model'] for m in models}
    except Exception:
        return set()

def load_models_from_json():
    """Charge la configuration depuis le fichier JSON central"""
    if not MODELS_JSON_PATH.exists():
        print(f"❌ Erreur critique : Fichier {MODELS_JSON_PATH} introuvable.")
        sys.exit(1)
        
    with open(MODELS_JSON_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)

def print_table(title, data):
    """Affiche un tableau ASCII formaté"""
    print(f"\n📊 {title}")
    print("+" + "-"*40 + "+" + "-"*15 + "+")
    print(f"| {'MÉTRIQUE':<38} | {'NOMBRE':^13} |")
    print("+" + "-"*40 + "+" + "-"*15 + "+")
    for label, value in data.items():
        print(f"| {label:<38} | {value:^13} |")
    print("+" + "-"*40 + "+" + "-"*15 + "+")
    print("")

def pull_with_progress(tag):
    """Télécharge un modèle avec une barre de progression tqdm"""
    current_digest = None
    pbar = None
    
    for progress in ollama.pull(tag, stream=True):
        digest = progress.get('digest', '')
        status = progress.get('status', '')
        
        if digest != current_digest and digest:
            if pbar:
                pbar.close()
            current_digest = digest
            pbar = tqdm(total=progress.get('total', 0), desc=f"      ⬇️  {status[:20]}...", unit='B', unit_scale=True, leave=False)
            
        if pbar:
            pbar.set_description(f"      ⬇️  {status}")
            completed = progress.get('completed', 0)
            if completed:
                pbar.n = completed
                pbar.refresh()
    
    if pbar:
        pbar.close()

def main():
    parser = argparse.ArgumentParser(description="Script de gestion de masse des modèles WaveLocalAI")
    parser.add_argument("--dry-run", action="store_true", help="Vérifie uniquement l'état sans télécharger")
    parser.add_argument("--force", action="store_true", help="Force le re-téléchargement si déjà présent")
    args = parser.parse_args()

    print("\n🌊 WAVESTONE LOCAL AI - SETUP MODELS")
    print("=====================================")

    # 1. Vérification connexion Ollama
    print("📡 Vérification de la connexion Ollama...", end=" ")
    if not check_ollama_connection():
        print("❌ ÉCHEC")
        print("   👉 Assurez-vous que l'application Ollama tourne (http://localhost:11434)")
        sys.exit(1)
    print("✅ OK")

    # 2. Récupération des modèles locaux
    installed_tags = get_installed_tags()
    
    # 3. Chargement depuis le JSON (Source of Truth)
    print(f"📂 Lecture de la configuration : {MODELS_JSON_PATH}")
    models_db = load_models_from_json()
    
    # Filtrage : On ne garde que les modèles 'local'
    targets = [info for info in models_db.values() if info.get('type') == 'local']
    
    print(f"📦 Modèles cibles dans le catalogue : {len(targets)}\n")
    print("-" * 70)

    stats = {
        "installed_pre": 0,
        "installed_new": 0,
        "failed": 0,
        "available": 0,
        "unavailable": 0
    }

    for i, model_info in enumerate(targets, 1):
        tag = model_info.get('ollama_tag')
        
        # Sécurité si le JSON est mal formé
        if not tag:
            print(f"[{i}/{len(targets)}] ⚠️  Entrée invalide (pas de tag), ignorée.")
            continue
            
        desc = model_info.get('desc', '')[:60] + "..."
        
        print(f"[{i}/{len(targets)}] {tag:<40}")
        print(f"      ℹ️  {desc}")

        is_installed = False
        # Vérification un peu lâche pour gérer les versions :latest implicites
        for installed in installed_tags:
            if tag == installed or f"{tag}:latest" == installed: 
                is_installed = True
                break

        # --- CAS 1 : DRY RUN ---
        if args.dry_run:
            if is_installed:
                print("      ✅ STATUT : DÉJÀ INSTALLÉ")
                stats["installed_pre"] += 1
            else:
                print("      ⚠️  STATUT : NON INSTALLÉ (Disponible pour installation)")
                stats["available"] += 1
            print("-" * 70)
            continue

        # --- CAS 2 : INSTALLATION RÉELLE ---
        if is_installed and not args.force:
            print("      ⏭️  ACTION : PASSÉ (Déjà présent)")
            stats["installed_pre"] += 1
            print("-" * 70)
            continue

        try:
            pull_with_progress(tag)
            print("      ✅ SUCCÈS : Téléchargement terminé")
            stats["installed_new"] += 1
        except Exception as e:
            print(f"      ❌ ÉCHEC : {e}")
            stats["failed"] += 1

        print("-" * 70)

    # --- SYNTHÈSE FINALE ---
    if args.dry_run:
        summary_data = {
            "Modèles déjà installés": stats["installed_pre"],
            "Disponibles pour installation": stats["available"],
            "Indisponibles": stats["unavailable"] 
        }
        print_table("SYNTHÈSE DU DRY-RUN", summary_data)
        if stats["available"] > 0:
            print(f"💡 Astuce : Lancez sans '--dry-run' pour installer les manquants.")
    else:
        summary_data = {
            "Modèles déjà présents": stats["installed_pre"],
            "Nouvellement installés": stats["installed_new"],
            "Échecs d'installation": stats["failed"]
        }
        print_table("SYNTHÈSE DE L'INSTALLATION", summary_data)

if __name__ == "__main__":
    main()