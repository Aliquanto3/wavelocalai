import os
from pathlib import Path

# --- CONFIGURATION ---

# Racine du projet (2 niveaux au-dessus du script)
ROOT_DIR = Path(__file__).parent.parent

# Fichier de sortie
OUTPUT_FILE = ROOT_DIR / "llm_review" / "REVIEW_ME.txt"

# Dossiers à ignorer (système, env, cache, git)
IGNORE_DIRS = {
    ".git", ".vscode", ".idea", "__pycache__", 
    "venv", ".venv", "env", "node_modules", 
    "dist", "build", "site-packages",
    "chroma_db", "data", "logs", "models" # On ignore les data et modèles
}

# Fichiers spécifiques ou extensions à ignorer
IGNORE_EXTENSIONS = {
    ".pyc", ".pyo", ".pyd", ".db", ".sqlite", ".sqlite3", 
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
    ".pdf", ".docx", ".xlsx", ".zip", ".tar", ".gz",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".gguf"
}

# FICHIERS À EXCLURE IMPÉRATIVEMENT (Sécurité Prompt Injection)
# On exclut le fichier de sortie lui-même et le dossier des prompts système
EXCLUDE_PATHS = [
    "llm_review/REVIEW_ME.txt",
    "llm_review/prompts" 
]

def is_ignored(path: Path) -> bool:
    """Vérifie si un chemin doit être ignoré."""
    # 1. Vérification des segments de dossier (ex: .venv, __pycache__)
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True
            
    # 2. Vérification des extensions de fichier
    if path.suffix.lower() in IGNORE_EXTENSIONS:
        return True
        
    # 3. Vérification des exclusions spécifiques (Relatif à la racine)
    try:
        rel_path = path.relative_to(ROOT_DIR).as_posix() # as_posix pour normaliser les slashs
        for exclude in EXCLUDE_PATHS:
            if rel_path.startswith(exclude):
                return True
    except ValueError:
        pass # Le chemin n'est pas relatif à la racine (ne devrait pas arriver)

    return False

def generate_project_tree(start_path: Path) -> str:
    """Génère une arborescence textuelle du projet."""
    tree_str = "📦 PROJECT STRUCTURE\n====================\n"
    
    for root, dirs, files in os.walk(start_path):
        root_path = Path(root)
        
        # Filtrage des dossiers in-place pour ne pas descendre dedans
        dirs[:] = [d for d in dirs if not is_ignored(root_path / d)]
        
        # Calcul de l'indentation
        level = len(root_path.relative_to(start_path).parts)
        indent = "    " * level
        tree_str += f"{indent}📁 {root_path.name}/\n"
        
        for f in files:
            file_path = root_path / f
            if not is_ignored(file_path):
                tree_str += f"{indent}    📄 {f}\n"
                
    return tree_str + "\n\n"

def collect_file_contents(start_path: Path) -> str:
    """Collecte le contenu de tous les fichiers non ignorés."""
    content_str = "📄 FILE CONTENTS\n================\n"
    
    for root, dirs, files in os.walk(start_path):
        root_path = Path(root)
        
        # Filtrage des dossiers
        dirs[:] = [d for d in dirs if not is_ignored(root_path / d)]
        
        for f in files:
            file_path = root_path / f
            
            if is_ignored(file_path):
                continue
                
            # Chemin relatif pour l'en-tête
            rel_path = file_path.relative_to(start_path).as_posix()
            
            content_str += f"\n{'='*80}\n"
            content_str += f"FILENAME: {rel_path}\n"
            content_str += f"{'='*80}\n"
            
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                content_str += text + "\n"
            except Exception as e:
                content_str += f"[ERROR READING FILE: {e}]\n"
                
    return content_str

def main():
    print(f"🔍 Scan du projet depuis : {ROOT_DIR}")
    print(f"🚫 Exclusion activée pour : {EXCLUDE_PATHS}")
    
    # Création du dossier de sortie si inexistant
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # Génération
    tree = generate_project_tree(ROOT_DIR)
    contents = collect_file_contents(ROOT_DIR)
    
    full_report = tree + contents
    
    # Écriture
    OUTPUT_FILE.write_text(full_report, encoding="utf-8")
    
    print(f"✅ Fichier de review généré avec succès : {OUTPUT_FILE}")
    print(f"📊 Taille du fichier : {OUTPUT_FILE.stat().st_size / 1024:.2f} KB")

if __name__ == "__main__":
    main()