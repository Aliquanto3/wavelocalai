import os
from collections.abc import Callable
from pathlib import Path

# --- CONFIGURATION ---

# Chemin du script actuel
SCRIPT_DIR = Path(__file__).parent

# Racine du projet (Ajustez .parent.parent selon où vous placez ce script !)
# Si le script est dans project/scripts/, utilisez .parent.parent
# Si le script est à la racine project/, utilisez .parent
ROOT_DIR = Path(__file__).parent.parent

# Dossier de sortie (À côté du script, comme demandé)
OUTPUT_DIR = SCRIPT_DIR / "exports"

# Définition des 4 fichiers de sortie
FILES_CONFIG = {
    "structure": OUTPUT_DIR / "01_PROJECT_STRUCTURE.txt",
    "docs": OUTPUT_DIR / "02_DOCUMENTATION.txt",
    "code": OUTPUT_DIR / "03_APP_CODE.txt",
    "tests": OUTPUT_DIR / "04_TESTS.txt",
}

# Dossiers à ignorer (système, env, cache, git)
IGNORE_DIRS = {
    ".git",
    ".vscode",
    ".idea",
    "__pycache__",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "site-packages",
    "chroma_db",
    "data",
    "logs",
    "models",
    "exports",
    "llm_review",  # On ignore les dossiers de sortie potentiels
}

# Fichiers spécifiques ou extensions à ignorer
IGNORE_EXTENSIONS = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".pdf",
    ".docx",
    ".xlsx",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".gguf",
    ".DS_Store",
}


def is_ignored(path: Path) -> bool:
    """Vérifie si un chemin doit être ignoré globalement."""
    # 1. Vérification des segments de dossier
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True

    # 2. Vérification des extensions de fichier
    return path.suffix.lower() in IGNORE_EXTENSIONS


def generate_project_tree(start_path: Path) -> str:
    """Génère l'arborescence complète du projet."""
    tree_str = "📦 PROJECT STRUCTURE\n====================\n"

    for root, dirs, files in os.walk(start_path):
        root_path = Path(root)

        # Filtrage des dossiers in-place
        dirs[:] = [d for d in dirs if not is_ignored(root_path / d)]

        # Calcul de l'indentation
        try:
            level = len(root_path.relative_to(start_path).parts)
        except ValueError:
            continue  # Si le chemin n'est pas relatif au start_path (cas rares)

        indent = "    " * level
        tree_str += f"{indent}📁 {root_path.name}/\n"

        for f in files:
            file_path = root_path / f
            if not is_ignored(file_path):
                tree_str += f"{indent}    📄 {f}\n"

    return tree_str + "\n"


def collect_file_contents(start_path: Path, filter_func: Callable[[Path], bool], title: str) -> str:
    """
    Collecte le contenu des fichiers qui correspondent à une fonction de filtre.
    """
    content_str = f"📄 {title}\n{'=' * len(title)}\n"
    file_count = 0

    for root, dirs, files in os.walk(start_path):
        root_path = Path(root)

        # Filtrage des dossiers pour ne pas descendre dans les dossiers ignorés
        dirs[:] = [d for d in dirs if not is_ignored(root_path / d)]

        for f in files:
            file_path = root_path / f

            # 1. Vérification globale (ignore)
            if is_ignored(file_path):
                continue

            # 2. Vérification spécifique (le filtre passé en argument)
            if not filter_func(file_path):
                continue

            file_count += 1

            try:
                rel_path = file_path.relative_to(start_path).as_posix()
            except ValueError:
                rel_path = file_path.name

            content_str += f"\n{'='*80}\n"
            content_str += f"FILENAME: {rel_path}\n"
            content_str += f"{'='*80}\n"

            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                content_str += text + "\n"
            except Exception as e:
                content_str += f"[ERROR READING FILE: {e}]\n"

    if file_count == 0:
        content_str += "\n(Aucun fichier trouvé pour cette catégorie)\n"

    return content_str


# --- FILTRES SPÉCIFIQUES ---


def is_doc_file(path: Path) -> bool:
    return path.suffix.lower() == ".md"


def is_test_file(path: Path) -> bool:
    # C'est un test si c'est un .py ET qu'il est dans un dossier "tests"
    return path.suffix.lower() == ".py" and "tests" in path.parts


def is_app_code_file(path: Path) -> bool:
    # C'est du code applicatif si c'est un .py ET qu'il n'est PAS dans "tests"
    # Et ce n'est pas le script lui-même
    is_self = path.resolve() == Path(__file__).resolve()
    return path.suffix.lower() == ".py" and "tests" not in path.parts and not is_self


def main():
    print(f"🔍 Script localisé dans : {SCRIPT_DIR}")
    print(f"📂 Racine du projet analysée : {ROOT_DIR}")
    print(f"💾 Dossier d'export cible : {OUTPUT_DIR}")

    # Création du dossier de sortie
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Génération de l'architecture
    print("🏗️  Génération de l'architecture...")
    struct_content = generate_project_tree(ROOT_DIR)
    FILES_CONFIG["structure"].write_text(struct_content, encoding="utf-8")

    # 2. Génération de la documentation (.md)
    print("📚 Extraction de la documentation...")
    doc_content = collect_file_contents(ROOT_DIR, is_doc_file, "DOCUMENTATION (.md)")
    FILES_CONFIG["docs"].write_text(doc_content, encoding="utf-8")

    # 3. Génération du code applicatif (.py hors tests)
    print("💻 Extraction du code applicatif...")
    code_content = collect_file_contents(ROOT_DIR, is_app_code_file, "CODE APPLICATIF (.py)")
    FILES_CONFIG["code"].write_text(code_content, encoding="utf-8")

    # 4. Génération des tests (.py dans tests/)
    print("🧪 Extraction des tests...")
    test_content = collect_file_contents(ROOT_DIR, is_test_file, "TESTS")
    FILES_CONFIG["tests"].write_text(test_content, encoding="utf-8")

    print("\n✅ Export terminé avec succès ! Fichiers générés :")
    # Correction B007 : Utilisation de _ au lieu de key
    for _, path in FILES_CONFIG.items():
        if path.exists():
            size_kb = path.stat().st_size / 1024
            print(f"   - {path.name} ({size_kb:.2f} KB)")


if __name__ == "__main__":
    main()
