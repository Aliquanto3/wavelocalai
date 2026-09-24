#!/usr/bin/env python3
"""
📦 LLM Audit Export Tool - Version 2.0
=====================================

Script d'export intelligent pour préparer les audits LLM d'une application Python.
Génère des fichiers contextuels adaptés à chaque phase d'audit.

Usage:
    python prepare_review.py                    # Export complet (toutes phases)
    python prepare_review.py --phase 1          # Phase 1: Architecture
    python prepare_review.py --phase 2          # Phase 2: Qualité code
    python prepare_review.py --phase 3          # Phase 3: Sécurité & Performance
    python prepare_review.py --phase 4          # Phase 4: UX & Documentation
    python prepare_review.py --phase 5          # Phase 5: DevOps & Packaging
    python prepare_review.py --list-phases      # Afficher les phases disponibles
    python prepare_review.py --stats            # Afficher les statistiques du projet

Auteur: [Anaël YAHI]
Version: 2.0.0
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ============================================================================
# CONFIGURATION
# ============================================================================

# Chemin du script actuel
SCRIPT_DIR = Path(__file__).parent

# Racine du projet (ajuster selon l'emplacement du script)
# Si script dans project/scripts/ → .parent.parent
# Si script à la racine project/ → .parent
ROOT_DIR = Path(__file__).parent.parent

# Dossier de sortie
OUTPUT_DIR = SCRIPT_DIR / "exports"

# Dossiers à ignorer globalement
IGNORE_DIRS: set[str] = {
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
    "llm_review",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "htmlcov",
    ".tox",
    "eggs",
    "*.egg-info",
}

# Extensions à ignorer
IGNORE_EXTENSIONS: set[str] = {
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
    ".webp",
    ".pdf",
    ".docx",
    ".xlsx",
    ".pptx",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".7z",
    ".rar",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".bin",
    ".gguf",
    ".DS_Store",
    ".lock",
}

# Extensions de code source
CODE_EXTENSIONS: set[str] = {".py", ".pyx", ".pyi"}

# Extensions de configuration
CONFIG_EXTENSIONS: set[str] = {
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".ini",
    ".cfg",
    ".conf",
}

# Fichiers de configuration importants (noms exacts)
CONFIG_FILES: set[str] = {
    "requirements.txt",
    "requirements.in",
    "requirements-dev.txt",
    "requirements-dev.in",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".env.example",
    ".env.template",
    ".gitignore",
    ".dockerignore",
    ".pre-commit-config.yaml",
    "ruff.toml",
    ".ruff.toml",
    "mypy.ini",
    ".mypy.ini",
    "pytest.ini",
    "tox.ini",
    "MANIFEST.in",
    "LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
}


# ============================================================================
# STRUCTURES DE DONNÉES
# ============================================================================


@dataclass
class FileInfo:
    """Informations sur un fichier analysé."""

    path: Path
    relative_path: str
    extension: str
    size_bytes: int
    line_count: int
    category: str
    imports: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


@dataclass
class PhaseConfig:
    """Configuration d'une phase d'audit."""

    id: int
    name: str
    description: str
    prompts: list[str]
    file_filter: Callable[[Path, "ProjectAnalyzer"], bool]
    include_stats: bool = True
    include_imports_analysis: bool = False
    max_tokens_estimate: int = 100000


@dataclass
class ProjectStats:
    """Statistiques globales du projet."""

    total_files: int = 0
    total_lines: int = 0
    total_size_kb: float = 0.0
    files_by_category: dict[str, int] = field(default_factory=dict)
    lines_by_category: dict[str, int] = field(default_factory=dict)
    top_imports: list[tuple[str, int]] = field(default_factory=list)


# ============================================================================
# ANALYSEUR DE PROJET
# ============================================================================


class ProjectAnalyzer:
    """Analyse et exporte un projet Python pour audit LLM."""

    def __init__(self, root_dir: Path, output_dir: Path):
        self.root_dir = root_dir.resolve()
        self.output_dir = output_dir
        self.files: list[FileInfo] = []
        self.stats = ProjectStats()
        self._import_counter: dict[str, int] = defaultdict(int)

    def is_ignored(self, path: Path) -> bool:
        """Vérifie si un chemin doit être ignoré."""
        for part in path.parts:
            if (part in IGNORE_DIRS or part.startswith(".")) and part not in {
                ".env.example",
                ".env.template",
                ".pre-commit-config.yaml",
            }:
                return True
        return path.suffix.lower() in IGNORE_EXTENSIONS

    def categorize_file(self, path: Path) -> str:
        """Détermine la catégorie d'un fichier."""
        rel_parts = path.relative_to(self.root_dir).parts
        suffix = path.suffix.lower()
        name = path.name.lower()

        # Fichiers de configuration
        if name in CONFIG_FILES or suffix in CONFIG_EXTENSIONS:
            return "config"

        # Documentation
        if suffix == ".md":
            return "docs"

        # Tests
        if ("tests" in rel_parts or "test" in rel_parts) and suffix in CODE_EXTENSIONS:
            return "tests"

        # Scripts utilitaires
        if (
            "scripts" in rel_parts or "tools" in rel_parts or "utils" in rel_parts
        ) and suffix in CODE_EXTENSIONS:
            return "scripts"

        # Code applicatif (core/backend)
        if (
            "core" in rel_parts or "backend" in rel_parts or "lib" in rel_parts
        ) and suffix in CODE_EXTENSIONS:
            return "core"

        # Code interface (app/frontend)
        if (
            "app" in rel_parts or "pages" in rel_parts or "ui" in rel_parts
        ) and suffix in CODE_EXTENSIONS:
            return "app"

        # Code source générique
        if suffix in CODE_EXTENSIONS:
            return "code"

        # Autres
        return "other"

    def extract_python_info(
        self, path: Path, content: str
    ) -> tuple[list[str], list[str], list[str]]:
        """Extrait les imports, classes et fonctions d'un fichier Python."""
        imports = []
        classes = []
        functions = []

        for line in content.split("\n"):
            line = line.strip()

            # Imports
            if line.startswith("import ") or line.startswith("from "):
                # Extraire le module principal
                match = re.match(r"(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_\.]*)", line)
                if match:
                    module = match.group(1).split(".")[0]
                    imports.append(module)
                    self._import_counter[module] += 1

            # Classes
            elif line.startswith("class "):
                match = re.match(r"class\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
                if match:
                    classes.append(match.group(1))

            # Fonctions (niveau module uniquement, pas les méthodes)
            elif line.startswith("def ") and not line.startswith("    "):
                match = re.match(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)", line)
                if match:
                    functions.append(match.group(1))

        return imports, classes, functions

    def analyze(self) -> None:
        """Analyse complète du projet."""
        print(f"🔍 Analyse du projet : {self.root_dir}")

        for root, dirs, files in os.walk(self.root_dir):
            root_path = Path(root)

            # Filtrage des dossiers
            dirs[:] = [d for d in dirs if not self.is_ignored(root_path / d)]

            for filename in files:
                file_path = root_path / filename

                if self.is_ignored(file_path):
                    continue

                try:
                    rel_path = file_path.relative_to(self.root_dir).as_posix()
                except ValueError:
                    continue

                # Lecture du fichier
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    line_count = len(content.splitlines())
                    size_bytes = file_path.stat().st_size
                except Exception:
                    continue

                # Catégorisation
                category = self.categorize_file(file_path)

                # Extraction d'infos Python
                imports, classes, functions = [], [], []
                if file_path.suffix.lower() in CODE_EXTENSIONS:
                    imports, classes, functions = self.extract_python_info(file_path, content)

                # Création de l'objet FileInfo
                file_info = FileInfo(
                    path=file_path,
                    relative_path=rel_path,
                    extension=file_path.suffix.lower(),
                    size_bytes=size_bytes,
                    line_count=line_count,
                    category=category,
                    imports=imports,
                    classes=classes,
                    functions=functions,
                )
                self.files.append(file_info)

                # Mise à jour des stats
                self.stats.total_files += 1
                self.stats.total_lines += line_count
                self.stats.total_size_kb += size_bytes / 1024

                self.stats.files_by_category[category] = (
                    self.stats.files_by_category.get(category, 0) + 1
                )
                self.stats.lines_by_category[category] = (
                    self.stats.lines_by_category.get(category, 0) + line_count
                )

        # Top imports
        self.stats.top_imports = sorted(
            self._import_counter.items(), key=lambda x: x[1], reverse=True
        )[:20]

        print(
            f"✅ Analyse terminée : {self.stats.total_files} fichiers, "
            f"{self.stats.total_lines:,} lignes"
        )

    def generate_tree(self) -> str:
        """Génère l'arborescence du projet."""
        tree_lines = ["📦 PROJECT STRUCTURE", "=" * 50, ""]

        # Grouper par dossier parent
        structure: dict[str, list[str]] = defaultdict(list)
        for f in self.files:
            parent = str(Path(f.relative_path).parent)
            if parent == ".":
                parent = "(root)"
            structure[parent].append(f.relative_path)

        for folder in sorted(structure.keys()):
            tree_lines.append(f"📁 {folder}/")
            for filepath in sorted(structure[folder]):
                filename = Path(filepath).name
                tree_lines.append(f"    📄 {filename}")
            tree_lines.append("")

        return "\n".join(tree_lines)

    def generate_stats_report(self) -> str:
        """Génère un rapport de statistiques."""
        lines = [
            "📊 PROJECT STATISTICS",
            "=" * 50,
            "",
            f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"📁 Root: {self.root_dir}",
            "",
            "## Global Metrics",
            f"- Total files: {self.stats.total_files}",
            f"- Total lines: {self.stats.total_lines:,}",
            f"- Total size: {self.stats.total_size_kb:.2f} KB",
            "",
            "## Files by Category",
        ]

        for cat, count in sorted(self.stats.files_by_category.items()):
            lines.append(
                f"- {cat}: {count} files ({self.stats.lines_by_category.get(cat, 0):,} lines)"
            )

        lines.extend(
            [
                "",
                "## Top 20 Imported Modules",
            ]
        )
        for module, count in self.stats.top_imports:
            lines.append(f"- {module}: {count} imports")

        lines.extend(
            [
                "",
                "## Estimated Context Size",
                f"- Approximate tokens: ~{self.stats.total_lines * 4:,}",
                f"- Recommendation: {'Split by phase' if self.stats.total_lines > 5000 else 'Single export OK'}",
            ]
        )

        return "\n".join(lines)

    def export_files(
        self,
        filter_func: Callable[["FileInfo"], bool],
        output_path: Path,
        title: str,
        include_metadata: bool = True,
    ) -> int:
        """Exporte les fichiers filtrés vers un fichier de sortie."""
        filtered = [f for f in self.files if filter_func(f)]

        if not filtered:
            output_path.write_text(f"# {title}\n\n(Aucun fichier trouvé)\n", encoding="utf-8")
            return 0

        lines = [
            f"# {title}",
            f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"# Files: {len(filtered)}",
            f"# Total lines: {sum(f.line_count for f in filtered):,}",
            "",
        ]

        if include_metadata:
            lines.extend(
                [
                    "## FILE INDEX",
                    "| # | File | Lines | Category |",
                    "|---|------|-------|----------|",
                ]
            )
            for i, f in enumerate(filtered, 1):
                lines.append(f"| {i} | {f.relative_path} | {f.line_count} | {f.category} |")
            lines.extend(["", "---", ""])

        for f in filtered:
            content = f.path.read_text(encoding="utf-8", errors="ignore")

            lines.extend(
                [
                    "",
                    "=" * 80,
                    f"FILE: {f.relative_path}",
                    f"CATEGORY: {f.category} | LINES: {f.line_count}",
                ]
            )

            if f.classes or f.functions:
                if f.classes:
                    lines.append(f"CLASSES: {', '.join(f.classes)}")
                if f.functions:
                    lines.append(
                        f"FUNCTIONS: {', '.join(f.functions[:10])}{'...' if len(f.functions) > 10 else ''}"
                    )

            lines.extend(
                [
                    "=" * 80,
                    "",
                    content,
                ]
            )

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return len(filtered)


# ============================================================================
# DÉFINITION DES PHASES D'AUDIT
# ============================================================================


def create_phases(analyzer: ProjectAnalyzer) -> dict[int, PhaseConfig]:
    """Crée les configurations de phases d'audit."""

    # Phase 1: Architecture
    def filter_phase1(f: FileInfo) -> bool:
        return f.category in {"core", "app", "code", "config"}

    # Phase 2: Qualité du code
    def filter_phase2(f: FileInfo) -> bool:
        return f.category in {"core", "app", "code"}

    # Phase 3: Sécurité & Performance
    def filter_phase3(f: FileInfo) -> bool:
        return f.category in {"core", "app", "code", "config"}

    # Phase 4: UX & Documentation
    def filter_phase4(f: FileInfo) -> bool:
        return f.category in {"app", "docs"}

    # Phase 5: DevOps & Packaging
    def filter_phase5(f: FileInfo) -> bool:
        return f.category == "config" or f.relative_path in {
            "requirements.txt",
            "pyproject.toml",
            "setup.py",
            "Dockerfile",
            "docker-compose.yml",
        }

    return {
        1: PhaseConfig(
            id=1,
            name="Architecture & Modularité",
            description="Audit de la structure, séparation des responsabilités, patterns",
            prompts=["Architecture", "Cohérence interne"],
            file_filter=lambda p, a: filter_phase1(p),
            include_imports_analysis=True,
        ),
        2: PhaseConfig(
            id=2,
            name="Qualité du Code",
            description="Refactoring, duplication, conventions, typage",
            prompts=["Qualité code", "Tests"],
            file_filter=lambda p, a: filter_phase2(p),
        ),
        3: PhaseConfig(
            id=3,
            name="Sécurité & Performance",
            description="Vulnérabilités, injections, optimisations",
            prompts=["Sécurité", "Performance"],
            file_filter=lambda p, a: filter_phase3(p),
        ),
        4: PhaseConfig(
            id=4,
            name="UX & Documentation",
            description="Interface utilisateur, documentation technique et utilisateur",
            prompts=["UX/UI", "Documentation"],
            file_filter=lambda p, a: filter_phase4(p),
        ),
        5: PhaseConfig(
            id=5,
            name="DevOps & Industrialisation",
            description="CI/CD, packaging, dépendances, pre-commit",
            prompts=["DevOps", "Packaging"],
            file_filter=lambda p, a: filter_phase5(p),
        ),
    }


# ============================================================================
# EXPORTS SPÉCIALISÉS
# ============================================================================


def export_phase(analyzer: ProjectAnalyzer, phase: PhaseConfig) -> None:
    """Exporte les fichiers pour une phase d'audit spécifique."""
    output_path = (
        analyzer.output_dir / f"PHASE_{phase.id}_{phase.name.upper().replace(' ', '_')}.txt"
    )

    # Header avec contexte
    header_lines = [
        f"# AUDIT PHASE {phase.id}: {phase.name}",
        f"# {phase.description}",
        "#" + "=" * 78,
        "",
        "## PROMPTS À UTILISER",
    ]
    for prompt in phase.prompts:
        header_lines.append(f"- {prompt}")

    header_lines.extend(
        [
            "",
            "## INSTRUCTIONS",
            "Analysez le code ci-dessous selon les critères du prompt d'audit correspondant.",
            "Concentrez-vous sur les aspects spécifiques à cette phase.",
            "",
            "---",
            "",
        ]
    )

    # Stats de la phase
    header_lines.append(analyzer.generate_stats_report())
    header_lines.extend(["", "---", ""])

    # Structure du projet
    header_lines.append(analyzer.generate_tree())
    header_lines.extend(["", "---", ""])

    # Contenu des fichiers
    content_lines = []
    filtered = [f for f in analyzer.files if phase.file_filter(f, analyzer)]

    content_lines.append(f"\n## CODE SOURCE ({len(filtered)} fichiers)\n")

    for f in filtered:
        try:
            content = f.path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        content_lines.extend(
            [
                "",
                "=" * 80,
                f"FILE: {f.relative_path}",
                f"CATEGORY: {f.category} | LINES: {f.line_count}",
            ]
        )

        if f.classes:
            content_lines.append(f"CLASSES: {', '.join(f.classes)}")
        if f.functions and len(f.functions) <= 15:
            content_lines.append(f"FUNCTIONS: {', '.join(f.functions)}")

        content_lines.extend(
            [
                "=" * 80,
                "",
                content,
            ]
        )

    # Écriture
    full_content = "\n".join(header_lines + content_lines)
    output_path.write_text(full_content, encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"  ✅ {output_path.name}: {len(filtered)} fichiers, {size_kb:.1f} KB")


def export_all_phases(analyzer: ProjectAnalyzer) -> None:
    """Exporte tous les fichiers pour toutes les phases."""
    phases = create_phases(analyzer)

    print("\n📦 Export par phase...")
    for _phase_id, phase in phases.items():
        export_phase(analyzer, phase)

    # Export complet additionnel
    print("\n📦 Export complet (tous fichiers)...")

    # Structure
    struct_path = analyzer.output_dir / "00_STRUCTURE.txt"
    struct_path.write_text(analyzer.generate_tree(), encoding="utf-8")

    # Stats
    stats_path = analyzer.output_dir / "00_STATS.txt"
    stats_path.write_text(analyzer.generate_stats_report(), encoding="utf-8")

    # Documentation
    analyzer.export_files(
        lambda f: f.category == "docs",
        analyzer.output_dir / "ALL_DOCUMENTATION.txt",
        "DOCUMENTATION COMPLÈTE",
    )

    # Tests
    analyzer.export_files(
        lambda f: f.category == "tests", analyzer.output_dir / "ALL_TESTS.txt", "TESTS COMPLETS"
    )

    # Code complet
    analyzer.export_files(
        lambda f: f.category in {"core", "app", "code", "scripts"},
        analyzer.output_dir / "ALL_CODE.txt",
        "CODE SOURCE COMPLET",
    )

    # Configuration
    analyzer.export_files(
        lambda f: f.category == "config",
        analyzer.output_dir / "ALL_CONFIG.txt",
        "FICHIERS DE CONFIGURATION",
    )


def export_single_phase(analyzer: ProjectAnalyzer, phase_id: int) -> None:
    """Exporte uniquement une phase spécifique."""
    phases = create_phases(analyzer)

    if phase_id not in phases:
        print(f"❌ Phase {phase_id} inconnue. Phases disponibles: 1-5")
        sys.exit(1)

    print(f"\n📦 Export phase {phase_id}...")
    export_phase(analyzer, phases[phase_id])

    # Toujours inclure structure et stats
    struct_path = analyzer.output_dir / "00_STRUCTURE.txt"
    struct_path.write_text(analyzer.generate_tree(), encoding="utf-8")

    stats_path = analyzer.output_dir / "00_STATS.txt"
    stats_path.write_text(analyzer.generate_stats_report(), encoding="utf-8")


def list_phases() -> None:
    """Affiche la liste des phases disponibles."""
    print(
        """
📋 PHASES D'AUDIT DISPONIBLES
==============================

Phase 1: Architecture & Modularité
   └─ Séparation des responsabilités, patterns, extensibilité
   └─ Fichiers: core/, app/, config
   └─ Prompts: Architecture, Cohérence interne

Phase 2: Qualité du Code
   └─ Refactoring, duplication, conventions PEP8, typage
   └─ Fichiers: core/, app/, code source
   └─ Prompts: Qualité code, Tests

Phase 3: Sécurité & Performance
   └─ Vulnérabilités, injections, optimisations mémoire
   └─ Fichiers: tout le code + config
   └─ Prompts: Sécurité, Performance

Phase 4: UX & Documentation
   └─ Interface utilisateur, docs techniques et utilisateur
   └─ Fichiers: app/, docs/
   └─ Prompts: UX/UI, Documentation

Phase 5: DevOps & Industrialisation
   └─ CI/CD, packaging, dépendances, pre-commit
   └─ Fichiers: fichiers de configuration
   └─ Prompts: DevOps, Packaging

USAGE:
   python prepare_review.py --phase 1    # Export phase spécifique
   python prepare_review.py              # Export toutes les phases
"""
    )


def show_stats(analyzer: ProjectAnalyzer) -> None:
    """Affiche les statistiques du projet."""
    print(analyzer.generate_stats_report())

    print("\n📁 DÉTAIL PAR CATÉGORIE")
    print("-" * 50)

    by_category: dict[str, list[FileInfo]] = defaultdict(list)
    for f in analyzer.files:
        by_category[f.category].append(f)

    for cat in sorted(by_category.keys()):
        files = by_category[cat]
        total_lines = sum(f.line_count for f in files)
        print(f"\n{cat.upper()} ({len(files)} fichiers, {total_lines:,} lignes)")
        for f in sorted(files, key=lambda x: x.line_count, reverse=True)[:5]:
            print(f"  - {f.relative_path}: {f.line_count} lignes")
        if len(files) > 5:
            print(f"  ... et {len(files) - 5} autres fichiers")


# ============================================================================
# MAIN
# ============================================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export intelligent pour audits LLM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python prepare_review.py                 # Export complet
  python prepare_review.py --phase 1       # Phase Architecture uniquement
  python prepare_review.py --stats         # Statistiques du projet
  python prepare_review.py --list-phases   # Liste des phases
        """,
    )
    parser.add_argument(
        "--phase",
        "-p",
        type=int,
        choices=[1, 2, 3, 4, 5],
        help="Numéro de la phase à exporter (1-5)",
    )
    parser.add_argument(
        "--list-phases", "-l", action="store_true", help="Afficher la liste des phases disponibles"
    )
    parser.add_argument(
        "--stats", "-s", action="store_true", help="Afficher les statistiques du projet"
    )
    parser.add_argument(
        "--root", "-r", type=Path, default=ROOT_DIR, help=f"Racine du projet (défaut: {ROOT_DIR})"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=OUTPUT_DIR,
        help=f"Dossier de sortie (défaut: {OUTPUT_DIR})",
    )

    args = parser.parse_args()

    # Affichage de l'aide des phases
    if args.list_phases:
        list_phases()
        return

    # Création de l'analyseur
    analyzer = ProjectAnalyzer(args.root, args.output)

    # Analyse du projet
    analyzer.analyze()

    # Mode stats uniquement
    if args.stats:
        show_stats(analyzer)
        return

    # Création du dossier de sortie
    args.output.mkdir(parents=True, exist_ok=True)

    # Export
    if args.phase:
        export_single_phase(analyzer, args.phase)
    else:
        export_all_phases(analyzer)

    print(f"\n✅ Export terminé dans: {args.output}")
    print("\n💡 Prochaines étapes:")
    print("   1. Ouvrir le fichier de la phase souhaitée")
    print("   2. Copier le contenu dans Claude avec le prompt correspondant")
    print("   3. Analyser les résultats et itérer")


if __name__ == "__main__":
    main()
