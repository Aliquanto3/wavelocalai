import ast
import os
from pathlib import Path

# Configuration des chemins
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "exports"
ROOT_DIR = SCRIPT_DIR.parent

# Création récursive du dossier d'export
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class SkeletonExtractor(ast.NodeVisitor):
    """Extrait la structure d'un fichier Python (Signatures et Docstrings)."""

    def __init__(self) -> None:
        self.skeleton: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.skeleton.append(ast.unparse(node))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        self.skeleton.append(ast.unparse(node))

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Extrait la classe et ses méthodes sans le corps."""
        self.skeleton.append(f"\nclass {node.name}:")
        if docstring := ast.get_docstring(node):
            self.skeleton.append(f'    """{docstring}"""')

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                self.visit_FunctionDef(item, indent="    ")

    def visit_FunctionDef(self, node: ast.FunctionDef, indent: str = "") -> None:
        """Extrait la signature de la fonction."""
        args = ast.unparse(node.args)
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        self.skeleton.append(f"{indent}def {node.name}({args}){returns}:")
        if docstring := ast.get_docstring(node):
            self.skeleton.append(f'{indent}    """{docstring}"""')
        self.skeleton.append(f"{indent}    pass")


def generate_project_map(root_dir: Path, output_path: Path) -> None:
    """Génère un squelette complet du projet en excluant le dossier d'audit.

    Args:
        root_dir (Path): Racine du projet à scanner.
        output_path (Path): Chemin du fichier de sortie.
    """
    output: list[str] = []
    exclude_dir = SCRIPT_DIR.name  # "llm_review"

    for root, dirs, files in os.walk(root_dir):
        # MODIFICATION CRITIQUE : On modifie dirs in-place pour que os.walk ne s'y aventure pas
        if exclude_dir in dirs:
            dirs.remove(exclude_dir)

        # Optionnel : exclure les environnements virtuels ou dossiers git
        for d in [".git", "__pycache__", ".venv", "venv"]:
            if d in dirs:
                dirs.remove(d)

        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                path = Path(root) / file
                output.append(f"\n{'='*20}\nFILE: {path.relative_to(root_dir)}\n{'='*20}")
                try:
                    with open(path, encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                        extractor = SkeletonExtractor()
                        extractor.visit(tree)
                        output.extend(extractor.skeleton)
                except Exception as e:
                    output.append(f"Error parsing {path}: {e}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output))


if __name__ == "__main__":
    output_file = OUTPUT_DIR / "audit_skeleton.txt"
    generate_project_map(ROOT_DIR, output_file)
    print(f"Squelette généré avec succès (excluant {SCRIPT_DIR.name}) dans : {output_file}")
